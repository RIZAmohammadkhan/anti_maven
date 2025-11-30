from pydantic import BaseModel
from typing import List, Optional, Union, Any

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
    why_to_buy: Optional[str] = None

class ResearchRequest(BaseModel):
    query: str

class ResearchResponse(BaseModel):
    products: List[Product]
    final_recommendation: str
