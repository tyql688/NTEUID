from gsuid_core.ai_core.configs.ai_config import ai_config

if ai_config.get_config("enable").data:
    from .game_info import register_game_info

    register_game_info()

    from . import (
        tools,  # noqa: F401
        everness,  # noqa: F401
    )
