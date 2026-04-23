from __future__ import annotations

import logging


class BaseAgent:
    name = "base"

    def __init__(self) -> None:
        self.logger = logging.getLogger(self.__class__.__name__)

