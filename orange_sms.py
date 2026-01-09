import requests
import time
import urllib.parse

class OrangeSMS:
    def __init__(self):
        # Credentials provided
        self.client_id = "AhS6IEIRaXjj8MOOwXcHptI1621B4kuU"
        self.client_secret = "wcHwyrYAuMTEuYelTXgCVUWoyCoSTxgY8XEvBDLswrhx"
        # The Basic Auth header you provided
        self.auth_header = "Basic QWhTNklFSVJhWGpqOE1PT3dYY0hwdEkxNjIxQjRrdVU6d2NId3lyWUF1TVRFdVllbFRYZ0NWVVdveUNvU1R4Z1k4WEV2QkRMc3dyaHg="
        
        # IMPORTANT: Replace with your actual Orange Sender Address
        # This must be the number registered with your Orange Developer app (e.g., tel:+237600000000)
        self.sender_address = "tel:+237689686224" 
        
        self.token_url = "https://api.orange.com/oauth/v3/token"
        self.base_url = "https://api.orange.com/smsmessaging/v1/outbound"
        
        self._token = None
        self._token_expiry = 0

    def _get_token(self):
        """
        Retrieves an OAuth 2.0 access token from Orange API.
        Tokens are cached until they expire.
        """
        if self._token and time.time() < self._token_expiry:
            return self._token

        headers = {
            "Authorization": self.auth_header,
            "Content-Type": "application/x-www-form-urlencoded",
            "Accept": "application/json"
        }
        data = {"grant_type": "client_credentials"}

        try:
            response = requests.post(self.token_url, headers=headers, data=data)
            response.raise_for_status()
            token_data = response.json()
            self._token = token_data['access_token']
            # Token usually expires in 3600s, set expiry with a 60s buffer
            self._token_expiry = time.time() + int(token_data.get('expires_in', 3600)) - 60
            return self._token
        except Exception as e:
            print(f"Error getting Orange Access Token: {e}")
            return None

    def send_sms(self, recipient_number, message):
        """
        Sends an SMS to the recipient.
        :param recipient_number: The phone number (e.g., +2376xxxxxxx)
        :param message: The text message content
        :return: Tuple (Success Boolean, Response/Error Message)
        """
        token = self._get_token()
        if not token:
            return False, "Could not authenticate with Orange API"

        # Ensure recipient number format (e.g., +237...)
        clean_number = str(recipient_number).strip()
        if not clean_number.startswith('+'):
            if clean_number.startswith('237'):
                clean_number = f"+{clean_number}"
            else:
                # Default to Cameroon code if missing
                clean_number = f"+237{clean_number}"
            
        # URL Encode the sender address for the path (tel:+237... -> tel%3A%2B237...)
        encoded_sender = urllib.parse.quote(self.sender_address)
        url = f"{self.base_url}/{encoded_sender}/requests"
        
        headers = {
            "Authorization": f"Bearer {token}",
            "Content-Type": "application/json",
            "Accept": "application/json"
        }
        
        payload = {
            "outboundSMSMessageRequest": {
                "address": f"tel:{clean_number}",
                "senderAddress": self.sender_address,
                "outboundSMSTextMessage": {
                    "message": message
                }
            }
        }

        try:
            response = requests.post(url, headers=headers, json=payload)
            if response.status_code == 201:
                return True, response.json()
            else:
                # Try to parse the error message for better readability
                try:
                    error_data = response.json()
                    if 'requestError' in error_data:
                        req_error = error_data['requestError']
                        if 'policyException' in req_error:
                            vars = req_error['policyException'].get('variables', [])
                            if vars:
                                return False, f"Orange Policy: {vars[0]}"
                            return False, f"Orange Policy: {req_error['policyException'].get('text', 'Unknown policy error')}"
                except:
                    pass
                return False, f"API Error ({response.status_code}): {response.text}"
        except Exception as e:
            return False, str(e)
