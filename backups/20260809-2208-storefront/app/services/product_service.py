import re
import secrets
from dataclasses import dataclass
from decimal import Decimal
from typing import Any

from sqlalchemy import func, or_, select
from sqlalchemy.orm import Session

from app.models.commerce import Inventory, Product
from app.schemas.product import ProductCreate, ProductUpdate


class ProductServiceError(Exception):
    pass


class ProductNotFoundError(ProductServiceError):
    pass


class ProductConflictError(ProductServiceError):
    pass


class ProductValidationError(ProductServiceError):
    pass


@dataclass(slots=True)
class ProductPage:
    items: list[Product]
    total: int
    page: int
    page_size: int
    total_pages: int


class ProductService:
    SORTABLE_FIELDS = {
        "id",
        "product_name",
        "sku",
        "slug",
        "selling_price",
        "mrp",
        "opening_stock",
        "created_at",
        "updated_at",
    }

    @staticmethod
    def normalize_optional_text(value: Any) -> Any:
        if isinstance(value, str):
            value = value.strip()
            return value or None
        return value

    @staticmethod
    def slugify(value: str) -> str:
        slug = value.strip().lower()
        slug = re.sub(r"[^a-z0-9]+", "-", slug)
        slug = re.sub(r"-{2,}", "-", slug)
        slug = slug.strip("-")

        if not slug:
            raise ProductValidationError(
                "Unable to generate a valid product slug."
            )

        return slug[:255]

    @staticmethod
    def normalize_sku(value: str) -> str:
        sku = re.sub(
            r"[^A-Z0-9_-]+",
            "-",
            value.strip().upper(),
        )
        sku = re.sub(r"-{2,}", "-", sku).strip("-")

        if not sku:
            raise ProductValidationError(
                "Unable to generate a valid SKU."
            )

        return sku[:100]

    @staticmethod
    def normalize_barcode(value: str | None) -> str | None:
        if value is None:
            return None

        barcode = re.sub(r"\s+", "", value.strip())

        if not barcode:
            return None

        if len(barcode) > 100:
            raise ProductValidationError(
                "Barcode cannot exceed 100 characters."
            )

        return barcode

    @staticmethod
    def validate_prices_and_stock(data: dict[str, Any]) -> None:
        mrp = Decimal(str(data.get("mrp", 0) or 0))
        selling_price = Decimal(
            str(data.get("selling_price", 0) or 0)
        )
        cost_price = Decimal(str(data.get("cost_price", 0) or 0))
        gst_percentage = Decimal(
            str(data.get("gst_percentage", 0) or 0)
        )

        opening_stock = int(data.get("opening_stock", 0) or 0)
        min_stock = int(data.get("min_stock", 0) or 0)
        max_stock = int(data.get("max_stock", 0) or 0)

        if mrp < 0:
            raise ProductValidationError(
                "MRP cannot be negative."
            )

        if selling_price < 0:
            raise ProductValidationError(
                "Selling price cannot be negative."
            )

        if cost_price < 0:
            raise ProductValidationError(
                "Cost price cannot be negative."
            )

        if selling_price > mrp:
            raise ProductValidationError(
                "Selling price cannot exceed MRP."
            )

        if not Decimal("0") <= gst_percentage <= Decimal("100"):
            raise ProductValidationError(
                "GST percentage must be between 0 and 100."
            )

        if opening_stock < 0:
            raise ProductValidationError(
                "Opening stock cannot be negative."
            )

        if min_stock < 0:
            raise ProductValidationError(
                "Minimum stock cannot be negative."
            )

        if max_stock < 0:
            raise ProductValidationError(
                "Maximum stock cannot be negative."
            )

        if max_stock and max_stock < min_stock:
            raise ProductValidationError(
                "Maximum stock cannot be less than minimum stock."
            )

    @classmethod
    def slug_exists(
        cls,
        db: Session,
        slug: str,
        exclude_product_id: int | None = None,
    ) -> bool:
        query = select(Product.id).where(
            func.lower(Product.slug) == slug.lower(),
            Product.deleted_at.is_(None),
        )

        if exclude_product_id is not None:
            query = query.where(Product.id != exclude_product_id)

        return db.scalar(query.limit(1)) is not None

    @classmethod
    def sku_exists(
        cls,
        db: Session,
        sku: str,
        exclude_product_id: int | None = None,
    ) -> bool:
        query = select(Product.id).where(
            func.lower(Product.sku) == sku.lower(),
            Product.deleted_at.is_(None),
        )

        if exclude_product_id is not None:
            query = query.where(Product.id != exclude_product_id)

        return db.scalar(query.limit(1)) is not None

    @classmethod
    def barcode_exists(
        cls,
        db: Session,
        barcode: str,
        exclude_product_id: int | None = None,
    ) -> bool:
        query = select(Product.id).where(
            Product.barcode == barcode,
            Product.deleted_at.is_(None),
        )

        if exclude_product_id is not None:
            query = query.where(Product.id != exclude_product_id)

        return db.scalar(query.limit(1)) is not None

    @classmethod
    def generate_unique_slug(
        cls,
        db: Session,
        product_name: str,
        exclude_product_id: int | None = None,
    ) -> str:
        base_slug = cls.slugify(product_name)
        slug = base_slug
        counter = 2

        while cls.slug_exists(
            db,
            slug,
            exclude_product_id=exclude_product_id,
        ):
            suffix = f"-{counter}"
            slug = f"{base_slug[:255 - len(suffix)]}{suffix}"
            counter += 1

        return slug

    @classmethod
    def generate_unique_sku(
        cls,
        db: Session,
        product_name: str,
        exclude_product_id: int | None = None,
    ) -> str:
        words = re.findall(r"[A-Za-z0-9]+", product_name.upper())
        prefix = "".join(word[:3] for word in words[:2])[:8]
        prefix = prefix or "PRD"

        for _ in range(100):
            candidate = cls.normalize_sku(
                f"{prefix}-{secrets.randbelow(900000) + 100000}"
            )

            if not cls.sku_exists(
                db,
                candidate,
                exclude_product_id=exclude_product_id,
            ):
                return candidate

        raise ProductConflictError(
            "Unable to generate a unique SKU."
        )

    @classmethod
    def generate_unique_barcode(
        cls,
        db: Session,
        exclude_product_id: int | None = None,
    ) -> str:
        for _ in range(100):
            first_twelve = (
                f"890{secrets.randbelow(1_000_000_000):09d}"
            )
            checksum = cls.ean13_checksum(first_twelve)
            candidate = f"{first_twelve}{checksum}"

            if not cls.barcode_exists(
                db,
                candidate,
                exclude_product_id=exclude_product_id,
            ):
                return candidate

        raise ProductConflictError(
            "Unable to generate a unique barcode."
        )

    @staticmethod
    def ean13_checksum(first_twelve_digits: str) -> int:
        if (
            len(first_twelve_digits) != 12
            or not first_twelve_digits.isdigit()
        ):
            raise ProductValidationError(
                "EAN-13 source must contain exactly 12 digits."
            )

        total = sum(
            int(digit) * (1 if index % 2 == 0 else 3)
            for index, digit in enumerate(first_twelve_digits)
        )

        return (10 - total % 10) % 10

    @classmethod
    def get_by_id(
        cls,
        db: Session,
        product_id: int,
        include_deleted: bool = False,
    ) -> Product:
        query = select(Product).where(Product.id == product_id)

        if not include_deleted:
            query = query.where(Product.deleted_at.is_(None))

        product = db.scalar(query)

        if product is None:
            raise ProductNotFoundError(
                f"Product {product_id} was not found."
            )

        return product

    @classmethod
    def list_products(
        cls,
        db: Session,
        search: str | None = None,
        category_id: int | None = None,
        brand_id: int | None = None,
        is_active: bool | None = None,
        page: int = 1,
        page_size: int = 20,
        sort_by: str = "created_at",
        sort_order: str = "desc",
    ) -> ProductPage:
        page = max(int(page), 1)
        page_size = min(max(int(page_size), 1), 100)

        if sort_by not in cls.SORTABLE_FIELDS:
            sort_by = "created_at"

        sort_order = (
            "asc"
            if str(sort_order).lower() == "asc"
            else "desc"
        )

        filters = [Product.deleted_at.is_(None)]

        if search:
            term = f"%{search.strip()}%"
            filters.append(
                or_(
                    Product.product_name.ilike(term),
                    Product.short_name.ilike(term),
                    Product.sku.ilike(term),
                    Product.slug.ilike(term),
                    Product.barcode.ilike(term),
                    Product.hsn_code.ilike(term),
                )
            )

        if category_id is not None:
            filters.append(Product.category_id == category_id)

        if brand_id is not None:
            filters.append(Product.brand_id == brand_id)

        if is_active is not None:
            filters.append(Product.is_active.is_(is_active))

        total_query = (
            select(func.count(Product.id))
            .where(*filters)
        )
        total = int(db.scalar(total_query) or 0)

        sort_columns = {
            "product_name": Product.name,
            "selling_price": Product.price,
            "mrp": Product.compare_at_price,
            "opening_stock": Inventory.quantity,
        }
        sort_column = sort_columns.get(
            sort_by,
            getattr(Product, sort_by, Product.created_at),
        )
        order_expression = (
            sort_column.asc()
            if sort_order == "asc"
            else sort_column.desc()
        )

        query = (
            select(Product)
            .outerjoin(Inventory, Inventory.product_id == Product.id)
            .where(*filters)
            .order_by(order_expression, Product.id.desc())
            .offset((page - 1) * page_size)
            .limit(page_size)
        )

        items = list(db.scalars(query).all())
        total_pages = (
            (total + page_size - 1) // page_size
            if total
            else 0
        )

        return ProductPage(
            items=items,
            total=total,
            page=page,
            page_size=page_size,
            total_pages=total_pages,
        )

    @classmethod
    def create_product(
        cls,
        db: Session,
        payload: ProductCreate,
    ) -> Product:
        data = payload.model_dump()

        for key, value in list(data.items()):
            data[key] = cls.normalize_optional_text(value)

        product_name = data["product_name"].strip()
        data["product_name"] = product_name

        supplied_slug = data.get("slug")
        data["slug"] = (
            cls.slugify(supplied_slug)
            if supplied_slug
            else cls.generate_unique_slug(db, product_name)
        )

        supplied_sku = data.get("sku")
        data["sku"] = (
            cls.normalize_sku(supplied_sku)
            if supplied_sku
            else cls.generate_unique_sku(db, product_name)
        )

        data["barcode"] = cls.normalize_barcode(
            data.get("barcode")
        )

        if not data["barcode"]:
            data["barcode"] = cls.generate_unique_barcode(db)

        cls.validate_prices_and_stock(data)

        if cls.slug_exists(db, data["slug"]):
            raise ProductConflictError(
                f"Slug '{data['slug']}' already exists."
            )

        if cls.sku_exists(db, data["sku"]):
            raise ProductConflictError(
                f"SKU '{data['sku']}' already exists."
            )

        if data["barcode"] and cls.barcode_exists(
            db,
            data["barcode"],
        ):
            raise ProductConflictError(
                f"Barcode '{data['barcode']}' already exists."
            )

        inventory_data = {
            "quantity": data.pop("opening_stock"),
            "low_stock_threshold": data.pop("min_stock"),
            "max_quantity": data.pop("max_stock"),
        }
        product = Product(**data)
        product.inventory = Inventory(**inventory_data)

        try:
            db.add(product)
            db.commit()
            db.refresh(product)
            return product
        except Exception:
            db.rollback()
            raise

    @classmethod
    def update_product(
        cls,
        db: Session,
        product_id: int,
        payload: ProductUpdate,
    ) -> Product:
        product = cls.get_by_id(db, product_id)
        data = payload.model_dump()

        for key, value in list(data.items()):
            data[key] = cls.normalize_optional_text(value)

        product_name = data["product_name"].strip()
        data["product_name"] = product_name

        supplied_slug = data.get("slug")
        data["slug"] = (
            cls.slugify(supplied_slug)
            if supplied_slug
            else cls.generate_unique_slug(
                db,
                product_name,
                exclude_product_id=product_id,
            )
        )

        supplied_sku = data.get("sku")
        data["sku"] = (
            cls.normalize_sku(supplied_sku)
            if supplied_sku
            else cls.generate_unique_sku(
                db,
                product_name,
                exclude_product_id=product_id,
            )
        )

        data["barcode"] = cls.normalize_barcode(
            data.get("barcode")
        )

        if not data["barcode"]:
            data["barcode"] = cls.generate_unique_barcode(
                db,
                exclude_product_id=product_id,
            )

        cls.validate_prices_and_stock(data)

        if cls.slug_exists(
            db,
            data["slug"],
            exclude_product_id=product_id,
        ):
            raise ProductConflictError(
                f"Slug '{data['slug']}' already exists."
            )

        if cls.sku_exists(
            db,
            data["sku"],
            exclude_product_id=product_id,
        ):
            raise ProductConflictError(
                f"SKU '{data['sku']}' already exists."
            )

        if data["barcode"] and cls.barcode_exists(
            db,
            data["barcode"],
            exclude_product_id=product_id,
        ):
            raise ProductConflictError(
                f"Barcode '{data['barcode']}' already exists."
            )

        inventory_data = {
            "quantity": data.pop("opening_stock"),
            "low_stock_threshold": data.pop("min_stock"),
            "max_quantity": data.pop("max_stock"),
        }

        for field_name, value in data.items():
            setattr(product, field_name, value)

        if product.inventory is None:
            product.inventory = Inventory(**inventory_data)
        else:
            for field_name, value in inventory_data.items():
                setattr(product.inventory, field_name, value)

        try:
            db.commit()
            db.refresh(product)
            return product
        except Exception:
            db.rollback()
            raise

    @classmethod
    def soft_delete_product(
        cls,
        db: Session,
        product_id: int,
    ) -> Product:
        product = cls.get_by_id(db, product_id)
        product.deleted_at = func.now()
        product.is_active = False

        try:
            db.commit()
            db.refresh(product)
            return product
        except Exception:
            db.rollback()
            raise

    @classmethod
    def toggle_product_status(
        cls,
        db: Session,
        product_id: int,
    ) -> Product:
        product = cls.get_by_id(db, product_id)
        product.is_active = not product.is_active

        try:
            db.commit()
            db.refresh(product)
            return product
        except Exception:
            db.rollback()
            raise
