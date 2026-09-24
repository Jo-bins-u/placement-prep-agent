import bcrypt
import random
import string
from flask_login import UserMixin
import database as db

def hash_password(password: str) -> str:
    salt = bcrypt.gensalt()
    hashed = bcrypt.hashpw(password.encode('utf-8'), salt)
    return hashed.decode('utf-8')

def check_password(password: str, hashed: str) -> bool:
    try:
        return bcrypt.checkpw(password.encode('utf-8'), hashed.encode('utf-8'))
    except ValueError:
        return False

def generate_otp(length: int = 6) -> str:
    return "".join(random.choices(string.digits, k=length))

import os
import smtplib
from email.mime.text import MIMEText
from email.mime.multipart import MIMEMultipart

def send_otp_email(email: str, otp: str):
    """
    Sends an OTP via email using SMTP.
    """
    mail_username = os.getenv("MAIL_USERNAME")
    mail_password = os.getenv("MAIL_PASSWORD", "").replace(" ", "")
    
    if not mail_username or not mail_password:
        print(f"\n{'='*40}")
        print(f"[WARNING] MAIL_USERNAME or MAIL_PASSWORD not set in .env")
        print(f"[EMAIL] WOULD HAVE SENT TO: {email}")
        print(f"[OTP] CODE: {otp}")
        print(f"{'='*40}\n")
        return

    try:
        msg = MIMEMultipart()
        msg['From'] = os.getenv("EMAIL_FROM", mail_username)
        msg['To'] = email
        msg['Subject'] = "Your Prepwise Verification Code"
        
        body = f"Hello,\n\nYour verification code for Prepwise is: {otp}\n\nThis code will expire in 10 minutes.\n\nBest,\nThe Prepwise Team"
        msg.attach(MIMEText(body, 'plain'))
        
        # Connect to Gmail SMTP server (can be parameterized if using other providers)
        mail_server = os.getenv("MAIL_SERVER", "smtp.gmail.com")
        mail_port = int(os.getenv("MAIL_PORT", 587))
        server = smtplib.SMTP(mail_server, mail_port)
        server.starttls()
        server.login(mail_username, mail_password)
        server.send_message(msg)
        server.quit()
        print(f"OTP successfully sent to {email}")
    except Exception as e:
        print(f"Failed to send email: {e}")


class User(UserMixin):
    def __init__(self, user_dict):
        self.id = user_dict["id"]
        self.email = user_dict["email"]
        self.password_hash = user_dict["password_hash"]
        self.is_verified = user_dict["is_verified"]
        self.created_at = user_dict["created_at"]

    @classmethod
    def get(cls, user_id):
        row = db.get_user_by_id(user_id)
        if row:
            return cls(row)
        return None
