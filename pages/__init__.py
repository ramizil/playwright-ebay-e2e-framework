"""
Pages Module
============

Page Object Model (POM) layer.  Each class maps to a distinct page on eBay.
"""

from pages.home_page import HomePage
from pages.search_results_page import SearchResultsPage
from pages.product_page import ProductPage
from pages.cart_page import CartPage

__all__ = [
    "HomePage",
    "SearchResultsPage",
    "ProductPage",
    "CartPage",
]
