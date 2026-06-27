from pydantic import BaseModel, Field, field_validator, ConfigDict
from typing import Optional, Dict, Any, Literal, List

from constants.business_types import SUPPLIER, CUSTOMER, INDIVIDUAL
from constants.geodata import MAX_LATITUDE, MIN_LATITUDE, MAX_LONGITUDE, MIN_LONGITUDE
from constants.currencies import CURRENCY_DICT

class GeoData(BaseModel):
    latitude: float
    longitude: float

    @field_validator("latitude")
    @classmethod
    def validate_latitude(cls, v: float) -> float:
        if not MIN_LATITUDE <= v <= MAX_LATITUDE:
            raise ValueError("Latitude must be between -90 and 90")
        return v

    @field_validator("longitude")
    @classmethod
    def validate_longitude(cls, v: float) -> float:
        if not MIN_LONGITUDE <= v <= MAX_LONGITUDE:
            raise ValueError("Longitude must be between -180 and 180")
        return v


class BusinessCreate(BaseModel):
    model_config = ConfigDict(extra="forbid")  
    # запрет лишних полей
    type: Literal[SUPPLIER, CUSTOMER]
    name: str = Field(..., min_length=1, max_length=255)
    currency: str = Field(..., min_length=1, max_length=100)
    @field_validator("currency")
    @classmethod
    def validate_currency(cls, v: str) -> str:
        if v not in CURRENCY_DICT:
            raise ValueError(f"Currency '{v}' is not supported")
        return v    
    description: Optional[str] = Field(max_length=255, default=None)
    address: Optional[str] = Field(max_length=255, default=None)    
    geodata: Optional[GeoData] = None
    language: Optional[str] = Field(min_length=1, max_length=5, default=None)
    timezone: Optional[str] = Field(min_length=1, max_length=100, default=None)
    schedule: Optional[Dict[str, Any]] = None


class IndividualCreate(BaseModel):
    model_config = ConfigDict(extra="forbid")  
    # запрет лишних полей
    name: str = Field(..., min_length=1, max_length=255)
    currency: str = Field(..., min_length=1, max_length=100)
    @field_validator("currency")
    @classmethod
    def validate_currency(cls, v: str) -> str:
        if v not in CURRENCY_DICT:
            raise ValueError(f"Currency '{v}' is not supported")
        return v
    geodata: Optional[GeoData] = None
    timezone: Optional[str] = Field(min_length=1, max_length=100, default=None)

class BusinessUpdate(BaseModel):
    model_config = ConfigDict(extra="ignore")
    # игноририование лишних полей
    add_languages: Optional[List[str]] = None
    description: Optional[Dict] = None
    address: Optional[Dict] = None
    timezone: Optional[str] = Field(min_length=1, max_length=100, default=None)
    geodata: Optional[GeoData] = None
    schedule: Optional[Dict[str, Any]] = None
    local_names: Optional[Dict] = None

class IndividualUpdate(BaseModel):
    model_config = ConfigDict(extra="ignore")

    currency: Optional[str] = Field(default=None, min_length=1, max_length=100)
    @field_validator("currency")
    @classmethod
    def validate_currency(cls, v: Optional[str]) -> Optional[str]:
        if v is None:
            return v
        if v not in CURRENCY_DICT:
            raise ValueError(f"Currency '{v}' is not supported")
        return v
    timezone: Optional[str] = Field(default=None, min_length=1, max_length=100)
    geodata: Optional[GeoData] = None