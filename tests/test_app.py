"""Tests for the kudos feature. Run with:  python -m unittest discover tests"""
import os
import sys
import tempfile
import unittest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from app import create_app  # noqa: E402

ADMIN, BEN, MEI = 1, 2, 3  # ids of the sample users


class KudosTests(unittest.TestCase):
    def setUp(self):
        # Each test gets a fresh, empty database file
        self.folder = tempfile.TemporaryDirectory()
        self.addCleanup(self.folder.cleanup)
        self.client = create_app(os.path.join(self.folder.name, "test.db")).test_client()

    def login(self, user_id):
        self.client.post("/login", data={"user_id": user_id})

    def send(self, recipient_id, message):
        return self.client.post("/api/kudos", json={"recipient_id": recipient_id, "message": message})

    def feed(self):
        return self.client.get("/api/kudos").get_json()["items"]

    def test_must_be_signed_in_to_send(self):
        self.assertEqual(self.send(MEI, "Thanks!").status_code, 401)

    def test_send_and_see_in_feed(self):
        self.login(BEN)
        self.assertEqual(self.send(MEI, "Great demo today").status_code, 201)
        item = self.feed()[0]
        self.assertEqual((item["sender"], item["recipient"], item["message"]),
                         ("Ben Carter", "Mei Lin", "Great demo today"))

    def test_validation(self):
        self.login(BEN)
        self.assertEqual(self.send(MEI, "   ").status_code, 400)        # empty message
        self.assertEqual(self.send(MEI, "x" * 501).status_code, 400)    # too long
        self.assertEqual(self.send(BEN, "Go me").status_code, 400)      # yourself
        self.assertEqual(self.send(999, "Hello").status_code, 404)      # unknown colleague
        self.assertEqual(self.send("abc", "Hello").status_code, 400)    # not an id
        self.assertEqual(self.feed(), [])

    def test_user_list_excludes_self(self):
        self.login(BEN)
        names = [u["name"] for u in self.client.get("/api/users").get_json()]
        self.assertNotIn("Ben Carter", names)
        self.assertEqual(len(names), 3)

    def test_feed_is_paginated_newest_first(self):
        self.login(BEN)
        for i in range(25):
            self.send(MEI, f"Kudos {i}")
        first = self.client.get("/api/kudos").get_json()
        self.assertEqual(len(first["items"]), 20)
        self.assertTrue(first["has_more"])
        self.assertEqual(first["items"][0]["message"], "Kudos 24")
        second = self.client.get("/api/kudos?page=2").get_json()
        self.assertEqual(len(second["items"]), 5)
        self.assertFalse(second["has_more"])

    def test_non_admin_cannot_moderate(self):
        self.login(BEN)
        kudos_id = self.send(MEI, "Nice work").get_json()["id"]
        self.assertEqual(self.client.patch(f"/api/admin/kudos/{kudos_id}", json={"is_visible": False}).status_code, 403)
        self.assertEqual(self.client.delete(f"/api/admin/kudos/{kudos_id}").status_code, 403)
        self.assertEqual(self.client.get("/api/admin/kudos").status_code, 403)

    def test_admin_can_hide_restore_and_delete(self):
        self.login(BEN)
        kudos_id = self.send(MEI, "Inappropriate text").get_json()["id"]
        self.login(ADMIN)
        # Hide: gone from the public feed, still visible to the admin with the reason recorded
        self.assertEqual(self.client.patch(f"/api/admin/kudos/{kudos_id}",
                                           json={"is_visible": False, "reason": "Off topic"}).status_code, 200)
        self.assertEqual(self.feed(), [])
        admin_view = self.client.get("/api/admin/kudos").get_json()[0]
        self.assertFalse(admin_view["is_visible"])
        self.assertEqual(admin_view["reason_for_moderation"], "Off topic")
        # Restore
        self.client.patch(f"/api/admin/kudos/{kudos_id}", json={"is_visible": True})
        self.assertEqual(len(self.feed()), 1)
        # Delete
        self.assertEqual(self.client.delete(f"/api/admin/kudos/{kudos_id}").status_code, 204)
        self.assertEqual(self.feed(), [])
        self.assertEqual(self.client.delete(f"/api/admin/kudos/{kudos_id}").status_code, 404)

    def test_message_is_escaped_on_the_page(self):
        # The page builds feed items with textContent, and the API returns the text unchanged
        self.login(BEN)
        self.send(MEI, "<script>alert(1)</script>")
        self.assertEqual(self.feed()[0]["message"], "<script>alert(1)</script>")
        self.assertNotIn(b"<script>alert(1)</script>", self.client.get("/").data)


if __name__ == "__main__":
    unittest.main()
