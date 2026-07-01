from fastapi import Request, status
from starlette.middleware.base import BaseHTTPMiddleware
from starlette.responses import JSONResponse, Response

from core.contants import LLM, LLM_MODELS


class RequiredHeadersMiddleware(BaseHTTPMiddleware):
    """Validate optional LLM-related headers when they are present."""

    async def dispatch(self, request: Request, call_next) -> Response:
        llm_temperature = request.headers.get("llm_temperature")
        llm = request.headers.get("llm")
        llm_model = request.headers.get("llm_model")

        if llm_temperature is not None:
            try:
                temperature = float(llm_temperature)
            except ValueError:
                return JSONResponse(
                    status_code=status.HTTP_400_BAD_REQUEST,
                    content={"detail": "`llm_temperature` must be a number between 0 and 1."},
                )

            if not 0 <= temperature <= 1:
                return JSONResponse(
                    status_code=status.HTTP_400_BAD_REQUEST,
                    content={"detail": "`llm_temperature` must be between 0 and 1."},
                )
            request.state.llm_temperature = temperature

        selected_llm: LLM | None = None
        if llm is not None:
            allowed_llms = {provider.value for provider in LLM}
            if llm not in allowed_llms:
                return JSONResponse(
                    status_code=status.HTTP_400_BAD_REQUEST,
                    content={"detail": f"`llm` must be one of: {', '.join(sorted(allowed_llms))}."},
                )
            selected_llm = LLM(llm)
            request.state.llm = selected_llm.value

        if llm_model is not None:
            if selected_llm is None:
                return JSONResponse(
                    status_code=status.HTTP_400_BAD_REQUEST,
                    content={"detail": "`llm_model` requires the `llm` header."},
                )

            allowed_models = LLM_MODELS[selected_llm]
            if llm_model not in allowed_models:
                return JSONResponse(
                    status_code=status.HTTP_400_BAD_REQUEST,
                    content={
                        "detail": (
                            f"`llm_model` is invalid for llm '{selected_llm.value}'. "
                            f"Allowed values: {', '.join(sorted(allowed_models))}."
                        )
                    },
                )
            request.state.llm_model = llm_model

        return await call_next(request)
