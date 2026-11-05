"""
Tests for restocking API endpoints and the procurement fields on demand forecasts.
"""
from datetime import datetime, timedelta

import pytest

from mock_data import restocking_orders


@pytest.fixture(autouse=True)
def clean_restocking_orders():
    """Restocking orders live in a module-level list, so clear it around each test."""
    restocking_orders.clear()
    yield
    restocking_orders.clear()


def get_forecast(client, sku):
    """Look up a forecast record by SKU."""
    forecasts = client.get("/api/demand").json()
    return next(f for f in forecasts if f["item_sku"] == sku)


class TestDemandProcurementFields:
    """Test suite for the cost/supplier/lead time fields added to forecasts."""

    def test_demand_forecast_procurement_fields(self, client):
        """Test that every forecast exposes cost, supplier and lead time."""
        data = client.get("/api/demand").json()
        assert len(data) > 0

        for forecast in data:
            assert isinstance(forecast["unit_cost"], (int, float))
            assert forecast["unit_cost"] > 0
            assert isinstance(forecast["supplier"], str)
            assert forecast["supplier"] != ""
            assert isinstance(forecast["lead_time_days"], int)
            assert forecast["lead_time_days"] > 0


class TestRestockingOrderEndpoints:
    """Test suite for restocking order endpoints."""

    def test_get_restocking_orders_empty(self, client):
        """Test listing orders before any have been submitted."""
        response = client.get("/api/restocking-orders")
        assert response.status_code == 200
        assert response.json() == []

    def test_create_restocking_order(self, client):
        """Test submitting a valid order."""
        response = client.post(
            "/api/restocking-orders",
            json={"items": [{"sku": "WDG-001", "quantity": 10}]},
        )
        assert response.status_code == 201

        order = response.json()
        assert order["id"] == "1"
        assert order["order_number"].startswith("RST-")
        assert order["order_number"].endswith("-0001")
        assert order["status"] == "Submitted"
        assert len(order["items"]) == 1
        assert order["items"][0]["sku"] == "WDG-001"
        assert order["items"][0]["quantity"] == 10

    def test_restocking_order_total_calculation(self, client):
        """Test that the total is computed from server-side unit costs."""
        widget = get_forecast(client, "WDG-001")
        gasket = get_forecast(client, "GSK-203")

        response = client.post(
            "/api/restocking-orders",
            json={"items": [
                {"sku": "WDG-001", "quantity": 10},
                {"sku": "GSK-203", "quantity": 25},
            ]},
        )
        order = response.json()

        expected = 10 * widget["unit_cost"] + 25 * gasket["unit_cost"]
        assert abs(order["total_value"] - expected) < 0.01

        # Unit cost on each line must match the forecast data
        by_sku = {item["sku"]: item for item in order["items"]}
        assert by_sku["WDG-001"]["unit_cost"] == widget["unit_cost"]
        assert by_sku["GSK-203"]["unit_cost"] == gasket["unit_cost"]

    def test_restocking_order_ignores_client_supplied_price(self, client):
        """Test that a price sent by the client is not used."""
        widget = get_forecast(client, "WDG-001")

        response = client.post(
            "/api/restocking-orders",
            json={"items": [{"sku": "WDG-001", "quantity": 1, "unit_cost": 0.01}]},
        )
        assert response.status_code == 201
        assert response.json()["items"][0]["unit_cost"] == widget["unit_cost"]

    def test_restocking_order_lead_time_is_longest_item(self, client):
        """Test that the order lead time is the maximum item lead time."""
        fast = get_forecast(client, "FLT-405")
        slow = get_forecast(client, "WDG-001")
        assert fast["lead_time_days"] < slow["lead_time_days"]

        response = client.post(
            "/api/restocking-orders",
            json={"items": [
                {"sku": "FLT-405", "quantity": 5},
                {"sku": "WDG-001", "quantity": 5},
            ]},
        )
        order = response.json()
        assert order["lead_time_days"] == slow["lead_time_days"]

    def test_restocking_order_expected_delivery(self, client):
        """Test that expected delivery equals submitted date plus lead time."""
        response = client.post(
            "/api/restocking-orders",
            json={"items": [{"sku": "GSK-203", "quantity": 5}]},
        )
        order = response.json()

        submitted = datetime.fromisoformat(order["submitted_date"])
        expected = datetime.fromisoformat(order["expected_delivery"])
        assert expected - submitted == timedelta(days=order["lead_time_days"])

    def test_create_restocking_order_empty_items(self, client):
        """Test that an order with no items is rejected."""
        response = client.post("/api/restocking-orders", json={"items": []})
        assert response.status_code == 400
        assert "detail" in response.json()

    @pytest.mark.parametrize("quantity", [0, -5])
    def test_create_restocking_order_invalid_quantity(self, client, quantity):
        """Test that zero or negative quantities are rejected."""
        response = client.post(
            "/api/restocking-orders",
            json={"items": [{"sku": "WDG-001", "quantity": quantity}]},
        )
        assert response.status_code == 400

    def test_create_restocking_order_unknown_sku(self, client):
        """Test that an unknown SKU returns 404."""
        response = client.post(
            "/api/restocking-orders",
            json={"items": [{"sku": "NOPE-999", "quantity": 1}]},
        )
        assert response.status_code == 404
        assert "not found" in response.json()["detail"].lower()

    def test_create_restocking_order_duplicate_sku(self, client):
        """Test that the same SKU twice in one order is rejected."""
        response = client.post(
            "/api/restocking-orders",
            json={"items": [
                {"sku": "WDG-001", "quantity": 1},
                {"sku": "WDG-001", "quantity": 2},
            ]},
        )
        assert response.status_code == 400

    def test_create_restocking_order_missing_body_field(self, client):
        """Test that a malformed body fails validation."""
        response = client.post("/api/restocking-orders", json={})
        assert response.status_code == 422

    def test_rejected_order_is_not_stored(self, client):
        """Test that a failed submission leaves no order behind."""
        client.post(
            "/api/restocking-orders",
            json={"items": [
                {"sku": "WDG-001", "quantity": 1},
                {"sku": "NOPE-999", "quantity": 1},
            ]},
        )
        assert client.get("/api/restocking-orders").json() == []

    def test_list_restocking_orders_newest_first(self, client):
        """Test that listed orders are sorted newest first."""
        first = client.post(
            "/api/restocking-orders",
            json={"items": [{"sku": "WDG-001", "quantity": 1}]},
        ).json()
        second = client.post(
            "/api/restocking-orders",
            json={"items": [{"sku": "GSK-203", "quantity": 1}]},
        ).json()

        data = client.get("/api/restocking-orders").json()
        assert [o["id"] for o in data] == [second["id"], first["id"]]
        assert second["order_number"] != first["order_number"]
