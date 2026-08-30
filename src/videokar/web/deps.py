"""How a route gets hold of the session.

Through the app rather than a closure, so the routes can live in their own
modules and still be reading the same state.
"""

from __future__ import annotations

from typing import Annotated

from fastapi import Depends, Request

from .session import Session


def session_of(request: Request) -> Session:
    return request.app.state.session


CurrentSession = Annotated[Session, Depends(session_of)]
"""Import this into a route module by name.

FastAPI resolves a handler's annotations against that module's globals, so the
alias has to be a name the module itself can see — not one reached through a
dotted path.
"""
