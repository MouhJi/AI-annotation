from pydantic import BaseModel, Field, model_validator

class SplitConfig(BaseModel):
    train: float = Field(default=80, ge=0, le=100)
    val: float = Field(default=10, ge=0, le=100)
    test: float = Field(default=10, ge=0, le=100)

    @model_validator(mode="after")
    def ratios_total_100(self):
        if abs(self.train + self.val + self.test - 100) > 0.001:
            raise ValueError("Train, validation, and test ratios must total 100")
        if self.train == 0:
            raise ValueError("Train ratio must be greater than 0")
        return self

class SplitSummary(BaseModel):
    train: int
    val: int
    test: int
    total: int
    configured: bool
