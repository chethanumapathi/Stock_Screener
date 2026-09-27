import json
import logging
import urllib.parse
import webbrowser
from datetime import datetime, time, timedelta
from kiteconnect import KiteConnect

import config

logger = logging.getLogger(__name__)


class KiteAuthManager:
    """
    Manages Zerodha Kite Connect authentication, daily session token caching,
    and automatic renewal.
    """

    def __init__(self, api_key: str = None, api_secret: str = None):
        self.api_key = api_key or config.KITE_API_KEY
        self.api_secret = api_secret or config.KITE_API_SECRET
        self.token_file = config.TOKEN_CACHE_FILE

        if not self.api_key or not self.api_secret:
            raise ValueError(
                "Kite API Key and API Secret must be provided. "
                "Please configure KITE_API_KEY and KITE_API_SECRET in your .env file."
            )

        self.kite = KiteConnect(api_key=self.api_key)

    def _is_token_from_today(self, token_data: dict) -> bool:
        """
        Check if the cached token was generated today after 06:00 AM IST.
        (Kite tokens expire daily around 06:00 AM IST).
        """
        created_at_str = token_data.get("created_at")
        if not created_at_str:
            return False

        try:
            created_at = datetime.fromisoformat(created_at_str)
            now = datetime.now()
            today_6am = datetime.combine(now.date(), time(6, 0, 0))

            if now < today_6am:
                # If current time is before 6 AM, token from yesterday after 6 AM is valid
                yesterday_6am = today_6am - timedelta(days=1)
                return created_at >= yesterday_6am
            else:
                # If current time is after 6 AM, token must be from today after 6 AM
                return created_at >= today_6am
        except Exception as e:
            logger.debug(f"Error parsing token timestamp: {e}")
            return False

    def _load_cached_token(self) -> str | None:
        """Load access token from cache file if valid."""
        if not self.token_file.exists():
            return None

        try:
            with open(self.token_file, "r", encoding="utf-8") as f:
                data = json.load(f)

            if self._is_token_from_today(data):
                access_token = data.get("access_token")
                if access_token:
                    logger.info("Found cached access token from today.")
                    return access_token
        except Exception as e:
            logger.warning(f"Failed to read cached token: {e}")

        return None

    def _save_cached_token(self, access_token: str, user_name: str = ""):
        """Save access token and timestamp to cache file."""
        data = {
            "access_token": access_token,
            "created_at": datetime.now().isoformat(),
            "user_name": user_name,
            "api_key": self.api_key,
        }
        try:
            with open(self.token_file, "w", encoding="utf-8") as f:
                json.dump(data, f, indent=2)
            logger.info(f"Saved active session token to {self.token_file}")
        except Exception as e:
            logger.warning(f"Failed to save token to cache: {e}")

    @staticmethod
    def extract_request_token(user_input: str) -> str:
        """
        Extract request_token from either raw token string or redirected URL.
        Example: http://127.0.0.1/?status=success&request_token=xyz123...
        """
        cleaned = user_input.strip()
        if "request_token=" in cleaned:
            parsed = urllib.parse.urlparse(cleaned)
            query_params = urllib.parse.parse_qs(parsed.query)
            token = query_params.get("request_token", [None])[0]
            if token:
                return token
        return cleaned

    def interactive_login(self) -> KiteConnect:
        """
        Directs user to the login URL, opens browser, prompts for request token,
        and generates daily access token.
        """
        login_url = self.kite.login_url()
        print("\n" + "=" * 70)
        print("ZERODHA KITE CONNECT AUTHENTICATION REQUIRED")
        print("=" * 70)
        print("\nOpening your browser to log in to Zerodha Kite...")
        print(f"\nIf your browser does not open automatically, visit this URL:\n\n  {login_url}\n")

        try:
            webbrowser.open(login_url)
        except Exception:
            pass

        print("After logging in, Zerodha will redirect to your registered Redirect URL.")
        print("Copy either the full redirected URL or the 'request_token' parameter value.")
        print("-" * 70)

        while True:
            raw_input = input("\nEnter the redirected URL or request_token: ").strip()
            if not raw_input:
                print("Input cannot be empty. Please try again.")
                continue

            request_token = self.extract_request_token(raw_input)
            if not request_token:
                print("Could not extract request_token. Please paste the full URL or token.")
                continue

            try:
                print("\nGenerating access token with Kite Connect API...")
                session_data = self.kite.generate_session(
                    request_token=request_token,
                    api_secret=self.api_secret,
                )
                access_token = session_data["access_token"]
                user_name = session_data.get("user_name", "")

                self.kite.set_access_token(access_token)
                self._save_cached_token(access_token, user_name)

                print(f"Authentication successful! Logged in as: {user_name or 'Zerodha User'}")
                print("=" * 70 + "\n")
                return self.kite
            except Exception as e:
                print(f"\n[ERROR] Authentication failed: {e}")
                retry = input("Would you like to try again? (y/n): ").strip().lower()
                if retry != "y":
                    raise SystemExit("Authentication aborted by user.")

    def get_kite_session(self, force_relogin: bool = False) -> KiteConnect:
        """
        Returns an authenticated KiteConnect client instance.
        Reuses cached session if valid, otherwise initiates interactive login.
        """
        if not force_relogin:
            cached_token = self._load_cached_token()
            if cached_token:
                self.kite.set_access_token(cached_token)
                try:
                    # Test token validity by fetching user profile
                    profile = self.kite.profile()
                    user_name = profile.get("user_name", "Zerodha User")
                    logger.info(f"Reusing active session for {user_name}.")
                    print(f"Reusing active Kite session (Logged in as: {user_name})")
                    return self.kite
                except Exception as e:
                    logger.warning(f"Cached token is expired or invalid ({e}). Requesting fresh login.")

        return self.interactive_login()


    def login_with_token(self, token_or_url: str) -> KiteConnect:
        """
        Generate session using a provided request_token or full redirect URL directly.
        """
        request_token = self.extract_request_token(token_or_url)
        if not request_token:
            raise ValueError("Invalid request_token or URL provided.")

        print(f"Generating session with request token: {request_token[:6]}...")
        session_data = self.kite.generate_session(
            request_token=request_token,
            api_secret=self.api_secret,
        )
        access_token = session_data["access_token"]
        user_name = session_data.get("user_name", "")

        self.kite.set_access_token(access_token)
        self._save_cached_token(access_token, user_name)

        print(f"Authentication successful! Logged in as: {user_name or 'Zerodha User'}")
        return self.kite


def get_authenticated_kite(force_relogin: bool = False) -> KiteConnect:
    """Helper to instantiate and return an authenticated Kite client."""
    manager = KiteAuthManager()
    return manager.get_kite_session(force_relogin=force_relogin)


if __name__ == "__main__":
    import sys
    manager = KiteAuthManager()
    if len(sys.argv) > 1:
        manager.login_with_token(sys.argv[1])
    else:
        manager.get_kite_session()
