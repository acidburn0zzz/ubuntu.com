from datetime import datetime
from typing import List, Dict, Optional

import pytz
from dateutil.parser import parse

from webapp.advantage.ua_contracts.helpers import (
    get_items_aggregated_values,
    get_machine_type,
    get_user_subscription_statuses,
    get_price_info,
    make_user_subscription_id,
    apply_entitlement_rules,
    group_shop_items,
)
from webapp.advantage.ua_contracts.primitives import (
    Contract,
    Account,
    Subscription,
    ContractItem,
)
from webapp.advantage.models import Listing, UserSubscription


def build_user_subscriptions(
    user_summary: List, listings: Dict[str, Listing]
) -> List[UserSubscription]:
    grouped_items = build_initial_user_subscriptions(user_summary, listings)
    user_subscriptions = build_final_user_subscriptions(grouped_items)

    return user_subscriptions


def build_initial_user_subscriptions(
    user_summary: List, listings: Dict[str, Listing]
) -> List:
    free_groups = build_free_item_groups(user_summary)
    trial_groups = build_trial_item_groups(user_summary, listings)
    shop_groups = build_shop_item_groups(user_summary, listings)
    legacy_groups = build_legacy_item_groups(user_summary)

    return free_groups + trial_groups + shop_groups + legacy_groups


def build_free_item_groups(user_summary: List) -> List:
    free_item_groups = []
    for user_details in user_summary:
        contracts: List[Contract] = user_details.get("contracts")

        for contract in contracts:
            if contract.product_id == "free":
                free_item_groups.append(
                    {
                        "account": user_details.get("account"),
                        "contract": contract,
                        "items": contract.items,
                        "listing": None,
                        "marketplace": "free",
                        "subscriptions": user_details.get("subscriptions"),
                        "type": "free",
                    }
                )

    return free_item_groups


def build_trial_item_groups(
    user_summary: List, listings: Dict[str, Listing]
) -> List:
    trial_item_groups = []
    for user_details in user_summary:
        contracts: List[Contract] = user_details.get("contracts")

        for contract in contracts:
            for item in contract.items:
                if item.reason == "trial_started":
                    listing = listings[item.product_listing_id]
                    trial_item_groups.append(
                        {
                            "account": user_details.get("account"),
                            "contract": contract,
                            "items": [item],
                            "listing": listing,
                            "marketplace": listing.marketplace,
                            "subscriptions": user_details.get("subscriptions"),
                            "type": "trial",
                        }
                    )

    return trial_item_groups


def build_shop_item_groups(
    user_summary: List, listings: Dict[str, Listing]
) -> List:
    shop_item_groups = []
    for user_details in user_summary:
        contracts: List[Contract] = user_details.get("contracts")

        for contract in contracts:
            # skip free contracts
            if contract.product_id == "free":
                continue

            # skip contracts without items
            if contract.items is None:
                continue

            raw_shop_groups = group_shop_items(items=contract.items)
            for key in raw_shop_groups:
                key_parts = key.split("||")
                listing_id = key_parts[0]
                subscription_id = key_parts[1]

                listing: Listing = listings[listing_id]
                items: List[ContractItem] = raw_shop_groups[key]

                shop_item_groups.append(
                    {
                        "account": user_details.get("account"),
                        "contract": contract,
                        "items": items,
                        "listing": listing,
                        "subscription_id": subscription_id,
                        "marketplace": listing.marketplace,
                        "subscriptions": user_details.get("subscriptions"),
                        "type": listing.period,
                    }
                )

    return shop_item_groups


def build_legacy_item_groups(user_summary: List) -> List:
    legacy_item_groups = []
    for user_details in user_summary:
        contracts: List[Contract] = user_details.get("contracts")

        for contract in contracts:
            # skip free contracts
            if contract.product_id == "free":
                continue

            # skip contracts without items
            if contract.items is None:
                continue

            for item in contract.items:
                if item.renewal is not None:
                    legacy_item_groups.append(
                        {
                            "account": user_details.get("account"),
                            "contract": contract,
                            "items": [item],
                            "listing": None,
                            "marketplace": "canonical-ua",
                            "subscriptions": user_details.get("subscriptions"),
                            "type": "legacy",
                        }
                    )

    return legacy_item_groups


def build_final_user_subscriptions(
    grouped_items: List,
) -> List[UserSubscription]:
    user_subscriptions = []
    for group in grouped_items:
        account: Account = group.get("account")
        listing: Listing = group.get("listing")
        contract: Contract = group.get("contract")
        subscriptions: List[Subscription] = group.get("subscriptions")
        items: List[ContractItem] = group.get("items")
        type = group.get("type")
        subscription_id = group.get("subscription_id")
        aggregated_values = get_items_aggregated_values(items)
        number_of_machines = aggregated_values.get("number_of_machines")
        price_info = get_price_info(number_of_machines, items, listing)
        renewal = items[0].renewal if type == "legacy" else None
        product_name = (
            contract.name if type != "free" else "Free Personal Token"
        )
        statuses = get_user_subscription_statuses(
            type=type,
            end_date=aggregated_values.get("end_date"),
            renewal=renewal,
            subscription_id=subscription_id,
            subscriptions=subscriptions or [],
            listing=listing or None,
        )

        id = make_user_subscription_id(
            account, type, contract, renewal, subscription_id
        )

        user_subscription = UserSubscription(
            id=id,
            type=type,
            account_id=account.id,
            entitlements=apply_entitlement_rules(contract.entitlements),
            start_date=aggregated_values.get("start_date"),
            end_date=aggregated_values.get("end_date"),
            number_of_machines=number_of_machines,
            product_name=product_name,
            marketplace=group.get("marketplace"),
            price=price_info.get("price"),
            currency=price_info.get("currency"),
            machine_type=get_machine_type(contract.product_id),
            contract_id=contract.id,
            subscription_id=subscription_id,
            listing_id=listing.id if listing else None,
            period=listing.period if listing else None,
            renewal_id=renewal.id if renewal else None,
            statuses=statuses,
        )

        # Do not return expired user subscriptions after 30 days
        show_user_subscription = True
        if type != "free":
            parsed_end_date = parse(user_subscription.end_date)
            time_now = datetime.utcnow().replace(tzinfo=pytz.utc)
            delta_till_expiry = parsed_end_date - time_now
            days_till_expiry = delta_till_expiry.days
            show_user_subscription = days_till_expiry >= -30

        if show_user_subscription:
            user_subscriptions.append(user_subscription)

    return user_subscriptions


def build_get_user_info(user_summary: dict = None) -> dict:
    subscription: Optional[Subscription] = user_summary["subscription"]

    if subscription is None:
        return {"has_monthly_subscription": False}

    renewal_info = user_summary["renewal_info"]

    if renewal_info is None:
        return {
            "has_monthly_subscription": True,
            "is_auto_renewing": False,
        }

    return {
        "has_monthly_subscription": True,
        "is_auto_renewing": subscription.is_auto_renewing,
        "last_payment_date": renewal_info.get("subscriptionStartOfCycle"),
        "next_payment_date": renewal_info.get("subscriptionEndOfCycle"),
        "total": renewal_info.get("total"),
        "currency": renewal_info.get("currency").upper(),
    }
