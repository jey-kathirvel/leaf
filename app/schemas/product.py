from decimal import Decimal
from typing import Optional

from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator


class ProductBase(BaseModel):
    product_name: str = Field(..., min_length=2, max_length=255)
    short_name: Optional[str] = Field(default=None, max_length=100)

    slug: str = Field(..., min_length=2, max_length=255)
    sku: str = Field(..., min_length=2, max_length=100)
    barcode: Optional[str] = Field(default=None, max_length=100)

    category_id: int
    brand_id: Optional[int] = None

    mrp: Decimal = Field(default=Decimal("0"))
    selling_price: Decimal = Field(default=Decimal("0"))
    cost_price: Decimal = Field(default=Decimal("0"))

    gst_percentage: Decimal = Field(default=Decimal("0"))
    hsn_code: Optional[str] = None

    track_inventory: bool = True
    opening_stock: int = 0
    min_stock: int = 0
    max_stock: int = 0

    short_description: Optional[str] = None
    long_description: Optional[str] = None

    meta_title: Optional[str] = None
    meta_description: Optional[str] = None
    meta_keywords: Optional[str] = None

    is_active: bool = True
    is_featured: bool = False
    is_new_arrival: bool = False
    is_best_seller: bool = False

    @field_validator(
        "product_name",
        "short_name",
        "slug",
        "sku",
        "barcode",
        "hsn_code",
        "meta_title",
        mode="before",
    )
    @classmethod
    def trim_strings(cls, value):
        if isinstance(value, str):
            value = value.strip()
            return value or None
        return value

    @model_validator(mode="after")
    def validate_prices(self):
        if self.selling_price > self.mrp:
            raise ValueError("Selling price cannot exceed MRP.")

        if self.gst_percentage < 0 or self.gst_percentage > 100:
            raise ValueError("GST must be between 0 and 100.")

        if self.opening_stock < 0:
            raise ValueError("Opening stock cannot be negative.")

        if self.min_stock < 0:
            raise ValueError("Minimum stock cannot be negative.")

        if self.max_stock < self.min_stock:
            raise ValueError(
                "Maximum stock cannot be less than minimum stock."
            )

        return self


class ProductCreate(ProductBase):
    pass


class ProductUpdate(ProductBase):
    pass


class ProductResponse(ProductBase):
    model_config = ConfigDict(from_attributes=True)

    id: int


class ProductList(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    product_name: str
    sku: str
    slug: str
    barcode: Optional[str]
    selling_price: Decimal
    opening_stock: int
    is_active: bool


class ProductSearch(BaseModel):
    search: Optional[str] = None
    category_id: Optional[int] = None
    brand_id: Optional[int] = None
    is_active: Optional[bool] = None
    page: int = 1
    page_size: int = 20
