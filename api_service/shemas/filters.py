from pydantic import BaseModel, Field, field_validator, ConfigDict
from typing import Optional, Dict, Any, Literal, List
from constants.default import MINIMAL_SEARCH_RADIUS_KM, MAXIMAL_SEARCH_RADIUS_KM

class IndividualProductCatalogFilters(BaseModel):
    model_config = ConfigDict(extra="forbid")

    keyword: Optional[str] = Field(max_length=50, default=None)
    hide_without_address: bool
    search_radius_km: Optional[float] = Field(
        default=None,
        ge=MINIMAL_SEARCH_RADIUS_KM,
        le=MAXIMAL_SEARCH_RADIUS_KM
    )
    all_categories: bool
    allowed_categories: List
    only_favorite_products: bool
    only_favorite_businesses: bool
    hide_without_price: bool
    hide_without_photo: bool
    supplier_id: Optional[int] = None

class CustomerProductCatalogFilters(BaseModel):
    model_config = ConfigDict(extra="forbid")

    keyword: Optional[str] = Field(max_length=50, default=None)
    hide_without_address: bool
    search_radius_km: Optional[float] = Field(
        default=None,
        ge=MINIMAL_SEARCH_RADIUS_KM,
        le=MAXIMAL_SEARCH_RADIUS_KM        
    )
    all_categories: bool
    allowed_categories: List
    only_favorite_products: bool
    only_favorite_businesses: bool
    hide_without_price: bool
    hide_without_photo: bool
    supplier_id: Optional[int] = None


class CounterAgentSearchFilters(BaseModel):
    model_config = ConfigDict(extra="forbid")

    keyword: Optional[str] = Field(max_length=50, default=None)
    hide_without_geodata: bool
    search_radius_km: Optional[float] = Field(
        default=None,
        ge=MINIMAL_SEARCH_RADIUS_KM,
        le=MAXIMAL_SEARCH_RADIUS_KM
    )
    only_favorite_businesses: bool
