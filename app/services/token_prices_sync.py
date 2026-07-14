from __future__ import annotations

import asyncio
import json
import logging
import math
from pathlib import Path

import httpx

from app.repositories.cost import SqlCostRepository

logger = logging.getLogger(__name__)

# Fuente PRIMARIA de precios. Es la que queda en vigor en la tabla token_prices.
# A diferencia de OpenRouter, expone el precio de caché (cache_read_input_token_cost)
# también para los alias base como "gpt-4o".
LITELLM_URL = (
    "https://raw.githubusercontent.com/BerriAI/litellm/main/"
    "model_prices_and_context_window.json"
)

# Fuente de VERIFICACIÓN. Solo se usa para comparar y, si difiere, emitir un log.
# Nunca sobreescribe el precio de LiteLLM.
OPENROUTER_URL = "https://openrouter.ai/api/v1/models"

# Snapshot local (formato OpenRouter) usado como respaldo de verificación si la
# API de OpenRouter no responde. El precio de LiteLLM no depende de este archivo.
OPENROUTER_FALLBACK_PATH = Path(__file__).parent.parent / "data" / "token_prices.json"

_HTTP_TIMEOUT = 30.0

# Tolerancia para considerar "iguales" dos precios entre fuentes. Relativa para
# absorber redondeos; el abs_tol pequeño hace que 0 vs no-cero siempre cuente como
# discrepancia (que es justo el caso de la caché ausente en OpenRouter).
_REL_TOL = 0.01
_ABS_TOL = 1e-9


def _to_per_million(value) -> float:
    try:
        return float(value or 0) * 1_000_000
    except (TypeError, ValueError):
        return 0.0


def _prices_match(a: float, b: float) -> bool:
    return math.isclose(a, b, rel_tol=_REL_TOL, abs_tol=_ABS_TOL)


async def _fetch_litellm(client: httpx.AsyncClient) -> dict[str, dict]:
    """Fuente primaria. Devuelve {model_name: {input, output, cache, provider}}
    con los precios ya expresados POR MILLÓN de tokens.
    """
    resp = await client.get(LITELLM_URL)
    resp.raise_for_status()
    data = resp.json()

    prices: dict[str, dict] = {}
    for name, spec in data.items():
        # "sample_spec" es una entrada de documentación, no un modelo. Las entradas
        # sin input_cost_per_token (imágenes, embeddings, etc.) no aplican aquí.
        if name == "sample_spec" or not isinstance(spec, dict):
            continue
        if "input_cost_per_token" not in spec:
            continue

        prices[name] = {
            "input": _to_per_million(spec.get("input_cost_per_token")),
            "output": _to_per_million(spec.get("output_cost_per_token")),
            "cache": _to_per_million(spec.get("cache_read_input_token_cost")),
            "provider": spec.get("litellm_provider"),
        }
    return prices


async def _fetch_openrouter_index(client: httpx.AsyncClient) -> dict[str, dict]:
    """Fuente de verificación. Devuelve un índice {id: {input, output, cache}}
    indexado tanto por el id completo (p.ej. "openai/gpt-4o") como por el sufijo
    tras la última "/" (p.ej. "gpt-4o"), para poder casar con los nombres de LiteLLM.
    """
    payload = None
    try:
        resp = await client.get(OPENROUTER_URL)
        resp.raise_for_status()
        payload = resp.json()
    except Exception as e:
        logger.warning(
            "OpenRouter no disponible para verificación (%s); usando snapshot local", e
        )
        try:
            with open(OPENROUTER_FALLBACK_PATH) as f:
                payload = json.load(f)
        except Exception as e2:
            logger.warning("Snapshot local de OpenRouter no disponible (%s)", e2)
            return {}

    models = payload["data"] if isinstance(payload, dict) else payload
    index: dict[str, dict] = {}
    for m in models:
        mid = m.get("id")
        if not mid:
            continue
        pricing = m.get("pricing") or {}
        entry = {
            "input": _to_per_million(pricing.get("prompt")),
            "output": _to_per_million(pricing.get("completion")),
            "cache": _to_per_million(pricing.get("input_cache_read")),
        }
        index[mid] = entry
        # Indexar también por sufijo sin pisar una coincidencia de id completo.
        index.setdefault(mid.split("/", 1)[-1], entry)
    return index


def _lookup_openrouter(index: dict[str, dict], name: str, provider: str | None):
    """Busca el modelo de LiteLLM dentro del índice de OpenRouter probando primero
    "<provider>/<name>" y luego el "<name>" desnudo.
    """
    candidates = []
    if provider:
        candidates.append(f"{provider}/{name}")
    candidates.append(name)
    for c in candidates:
        if c in index:
            return c, index[c]
    return None, None


async def token_prices_sync_task(
    cost_repo: SqlCostRepository,
    interval_hours: int = 24,
) -> None:
    while True:
        try:
            async with httpx.AsyncClient(timeout=_HTTP_TIMEOUT) as client:
                litellm_prices = await _fetch_litellm(client)
                openrouter_index = await _fetch_openrouter_index(client)

            synced = 0
            mismatches = 0
            for name, p in litellm_prices.items():
                # 1) El precio que QUEDA EN VIGOR es siempre el de LiteLLM.
                await cost_repo.upsert_token_price(
                    model_name=name,
                    input_price_per_million=p["input"],
                    output_price_per_million=p["output"],
                    cache_price_per_million=p["cache"],
                )
                synced += 1

                # 2) Verificación contra OpenRouter: si input, caché u output no
                #    coinciden, se emite un log y nada más. No se altera el precio.
                or_name, or_p = _lookup_openrouter(
                    openrouter_index, name, p["provider"]
                )
                if or_p is None:
                    continue

                if not (
                    _prices_match(p["input"], or_p["input"])
                    and _prices_match(p["cache"], or_p["cache"])
                    and _prices_match(p["output"], or_p["output"])
                ):
                    mismatches += 1
                    logger.warning(
                        "Discrepancia de precios %s (LiteLLM) vs %s (OpenRouter) "
                        "[USD por millón] input=%.6f/%.6f cache=%.6f/%.6f "
                        "output=%.6f/%.6f - se mantiene el de LiteLLM",
                        name,
                        or_name,
                        p["input"],
                        or_p["input"],
                        p["cache"],
                        or_p["cache"],
                        p["output"],
                        or_p["output"],
                    )

            # upsert_token_price solo hace flush; persistir para otras conexiones.
            await cost_repo.commit()
            logger.info(
                "Synced %d token prices (LiteLLM); %d discrepancias vs OpenRouter",
                synced,
                mismatches,
            )
        except Exception as e:
            logger.error(f"Error syncing token prices: {e}", exc_info=True)

        await asyncio.sleep(interval_hours * 3600)
