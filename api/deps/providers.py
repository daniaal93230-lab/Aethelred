from pydantic import BaseModel


class Services(BaseModel):
    """
    Global dependency container attached to app.state.services.
    """

    db: object
    risk: object
    exchange: object
    engine: object  # raw execution engine
    engine_orchestrator: object  # async orchestrator loop

    class Config:
        arbitrary_types_allowed = True
