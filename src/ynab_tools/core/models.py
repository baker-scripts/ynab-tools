"""Shared Pydantic models for YNAB data structures."""

from __future__ import annotations

from datetime import date

from pydantic import BaseModel, Field


class Account(BaseModel):
    """YNAB account."""

    id: str
    name: str
    type: str
    balance: int = Field(description="Balance in milliunits")
    cleared_balance: int = Field(default=0, description="Cleared balance in milliunits")
    closed: bool = False
    deleted: bool = False


class ScheduledTransaction(BaseModel):
    """YNAB scheduled transaction."""

    id: str
    account_id: str
    amount: int = Field(description="Amount in milliunits")
    payee_name: str | None = None
    date_next: str | None = None
    date_first: str | None = None
    frequency: str = "never"
    transfer_account_id: str | None = None
    deleted: bool = False
    memo: str | None = None


class TransactionOccurrence(BaseModel):
    """A single occurrence of a scheduled transaction within the projection window."""

    date: date
    amount: float = Field(description="Amount in dollars")
    payee: str
    transfer_account_id: str | None = None
    frequency: str
    label: str


class CreditCardPayment(BaseModel):
    """Credit card payment details."""

    name: str
    amount: float = Field(description="Payment amount in dollars")
    source: str = "category_balance"
    scheduled: bool = False


class Category(BaseModel):
    """YNAB budget category."""

    id: str
    name: str
    balance: int = Field(default=0, description="Balance in milliunits")
    activity: int = Field(default=0, description="Activity in milliunits")
    category_group_name: str = ""
    hidden: bool = False
    deleted: bool = False


class Transaction(BaseModel):
    """YNAB transaction."""

    id: str
    account_id: str
    amount: int = Field(description="Amount in milliunits")
    date: str
    payee_name: str | None = None
    memo: str | None = None
    cleared: str = ""
    approved: bool = False
    deleted: bool = False
    transfer_account_id: str | None = None
