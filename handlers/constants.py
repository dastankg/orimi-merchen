POST_TYPE_CHOICES = [
    "РМП_чай_ДО",
    "РМП_чай_ПОСЛЕ", 
    "РМП_кофе_ДО",
    "РМП_кофе_ПОСЛЕ",
    "ДМП_ОРИМИ КР",
    "ДМП_конкурент"
]

ORIMI_BRANDS = [
    "Tess",
    "Гринф",
    "ЖН",
    "Шах",
]

COMPETITOR_BRANDS = [
    "Beta",
    "Пиала",
    "Ахмад",
    "Jacobs",
    "Nestle",
]

def validate_post_type(post_type: str) -> bool:
    return post_type in POST_TYPE_CHOICES

def validate_orimi_brand(brand: str) -> bool:
    return brand in ORIMI_BRANDS

def validate_competitor_brand(brand: str) -> bool:
    return brand in COMPETITOR_BRANDS