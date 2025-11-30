from pydantic import BaseModel
from typing import List, Optional, Union, Any

class RetailerPrice(BaseModel):
    retailer: str
    price: Union[str, float, int]
    url: str
    availability: Optional[str] = "In Stock"

class Product(BaseModel):
    name: str
    price: Union[str, float, int]
    rating: Union[float, str, None] = None
    reviews_count: Union[int, str, None] = None
    features: Union[List[str], Any] = []
    pros: List[str] = []
    cons: List[str] = []
    url: Optional[str] = ""
    image_url: Optional[str] = None
    image_urls: List[str] = []  # Multiple product images
    why_to_buy: Optional[str] = None
    price_comparison: List[RetailerPrice] = []  # Prices from different retailers
    cheapest_link: Optional[str] = None  # Direct link to cheapest option

class ResearchRequest(BaseModel):
    query: str

class ResearchResponse(BaseModel):
    products: List[Product]
    final_recommendation: str
