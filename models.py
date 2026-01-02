from pydantic import BaseModel, Field
from typing import List, Optional, Union, Any

class RetailerPrice(BaseModel):
    retailer: str
    price: Union[str, float, int]
    url: str
    availability: Optional[str] = "In Stock"

class Product(BaseModel):
    name: str
    price: Union[str, float, int]
    rating: Optional[float] = None
    reviews_count: Optional[int] = None
    features: Union[List[str], Any] = Field(default_factory=list)
    pros: List[str] = Field(default_factory=list)
    cons: List[str] = Field(default_factory=list)
    url: Optional[str] = ""
    image_url: Optional[str] = None
    image_data: Optional[str] = None
    why_to_buy: Optional[str] = None
    price_comparison: List[RetailerPrice] = Field(default_factory=list)
    cheapest_link: Optional[str] = None

class ResearchRequest(BaseModel):
    query: str

class ResearchResponse(BaseModel):
    products: List[Product]
    final_recommendation: str
