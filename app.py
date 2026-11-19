import xml.etree.ElementTree as ET
import base64
import mimetypes
import sys
import html
import io
import csv
import json
import re
import math
import os
import traceback
import uuid
import enum
import random
import smtplib

#import docx
from icalendar import Calendar 
from email.mime.text import MIMEText
from email.mime.multipart import MIMEMultipart
from email.message import EmailMessage  # poprawne kodowanie nagłówków UTF-8 (polskie znaki w Subject)
import threading  # Do wysyłania w tle
from datetime import datetime, timedelta, date, time
from functools import wraps
from math import exp
from zoneinfo import ZoneInfo
import functools  # Potrzebne dla dekoratora login_required
from flask import Flask, jsonify, request, g, session, redirect, url_for, send_from_directory, send_file, \
    render_template, Blueprint, flash, Response, has_request_context  # Dodano flash
import joblib
import pandas as pd
import psycopg2
import requests
import psutil
from PIL import Image
from psycopg2.extras import RealDictCursor
from werkzeug.utils import secure_filename
from requests.exceptions import ReadTimeout, RequestException
import urllib3
import google.generativeai as genai
import unidecode
from geopy.exc import GeocoderTimedOut
from flask_cors import CORS

from contextlib import contextmanager
from psycopg2 import errorcodes
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.ext.associationproxy import association_proxy
from sqlalchemy import (Column, DateTime, ForeignKey, Integer, String, Table,
                        Boolean, Float, Time, create_engine, func, text, bindparam, TIMESTAMP, Date, desc,
                        UniqueConstraint, select, ARRAY, Enum, TEXT, extract, Text, CheckConstraint)
from sqlalchemy.orm import declarative_base, selectinload, sessionmaker, scoped_session, relationship, joinedload, aliased
from sqlalchemy.exc import IntegrityError
from geopy.distance import geodesic
from werkzeug.security import generate_password_hash, check_password_hash
# from dotenv import load_dotenv
from dotenv import load_dotenv
from flask_login import login_required, current_user, LoginManager, UserMixin, login_user
import secrets
import string
from flask_mail import Mail, Message
from geopy.geocoders import Nominatim
from time import sleep
import pdfplumber
import pytesseract
from pdf2image import convert_from_path
import logging

logging.basicConfig(level=logging.DEBUG)


print("--- SERWER ZALADOWAL NAJNOWSZA WERSJE PLIKU ---")
#
load_dotenv()  # Wczytaj zmienne z .env (w tym OPENAI_API_KEY)

# === ⭐️ IMPORT NOWEJ LOGIKI AI ⭐️ ===
# Używamy ścieżki względnej z kropką
# from ai_services.ai_planner import handle_plan_request
urllib3.disable_warnings(urllib3.exceptions.InsecureRequestWarning)
# === KONFIGURACJA APLIKACJI ===
TZ = ZoneInfo("Europe/Warsaw")
# Główna instancja aplikacji
app = Flask(__name__, static_folder="static", static_url_path="",
            template_folder='templates')  # Określamy folder szablonów
            
# === HARMONOGRAM PRZYPOMNIEŃ O DZIENNIKU ===
# UWAGA: NIE konfiguruj tutaj APScheduler! check_and_send_journal_reminders jest
# zdefiniowane dopiero pod koniec pliku, więc scheduler.add_job(func=...) dawało
# NameError przy starcie — aplikacja w ogóle się nie uruchamiała i żadne
# automatyczne maile nie były wysyłane.
# JEDYNY scheduler to wątek na dole pliku: start_journal_reminder_scheduler()
# (każdy piątek 9:00 Europe/Warsaw, wszystkie firmy) — patrz koniec app.py.

login_manager = LoginManager()
login_manager.init_app(app)  # <--- TEJ LINIJKI PRAWDOPODOBNIE BRAKUJE
login_manager.login_view = 'auth.login_page'  # Przekierowanie gdy nie zalogowany

CORS(app, supports_credentials=True)  # supports_credentials=True jest ważne dla sesji
app.config['DEBUG'] = False

CENTRUM_PASSWORD = os.environ.get('ADMIN_PASSWORD')  # Zmieniłem nazwę dla jasności
CENTRUM_USERNAME = os.environ.get('ADMIN_USERNAME')  # Wczytaj nową zmienną

# Wczytywanie konfiguracji ze zmiennych środowiskowych
#DATABASE_URL = os.getenv("DATABASE_URL", "postgresql+psycopg2://postgres:EDUQ@localhost:5432/suo")
DATABASE_URL = os.getenv("DATABASE_URL")
GOOGLE_MAPS_API_KEY = os.getenv("GOOGLE_MAPS_API_KEY")
# Diagnostyka na górze:
if not GOOGLE_MAPS_API_KEY:
    print("--- OSTRZEŻENIE: Brak klucza Google Maps API w pliku .env ---")
else:
    print(f"--- KLUCZ ZAŁADOWANY: {GOOGLE_MAPS_API_KEY[:10]}... ---")

GOOGLE_AI_API_KEY = os.getenv("GOOGLE_AI_API_KEY")
# Sekretny klucz dla sesji - MUSI być ustawiony dla logowania
app.secret_key = os.environ.get('FLASK_SECRET_KEY', '4a87aef7ea2d5e256d20bea4fb2853612f09475c43cb841f')

# Ustawienia uploadu
UPLOAD_FOLDER = 'uploads/documents'
DIAGNOSIS_UPLOAD_FOLDER = 'uploads/diagnoses'
ALLOWED_EXTENSIONS = {'pdf', 'jpg', 'jpeg', 'png', 'doc', 'docx'}
MAX_FILE_SIZE = 10 * 1024 * 1024  # 10MB
# Konfiguracja folderu dla uchwał
RESOLUTIONS_UPLOAD_FOLDER = 'uploads/resolutions'
os.makedirs(RESOLUTIONS_UPLOAD_FOLDER, exist_ok=True)
app.config['RESOLUTIONS_UPLOAD_FOLDER'] = RESOLUTIONS_UPLOAD_FOLDER

os.makedirs(UPLOAD_FOLDER, exist_ok=True)
app.config['UPLOAD_FOLDER'] = UPLOAD_FOLDER
app.config['DIAGNOSIS_UPLOAD_FOLDER'] = DIAGNOSIS_UPLOAD_FOLDER
app.config['MAX_CONTENT_LENGTH'] = MAX_FILE_SIZE

os.makedirs(UPLOAD_FOLDER, exist_ok=True)
app.config['UPLOAD_FOLDER'] = UPLOAD_FOLDER
app.config['MAX_CONTENT_LENGTH'] = MAX_FILE_SIZE

if not DATABASE_URL:
    raise ValueError("DATABASE_URL environment variable is not set!")
if not app.secret_key or app.secret_key == '4a87aef7ea2d5e256d20bea4fb2853612f09475c43cb841f':
    print("=" * 50)
    print("OSTRZEŻENIE: Używasz domyślnego FLASK_SECRET_KEY. Zmień go w zmiennych środowiskowych!")
    print("=" * 50)

print(f"--- APLIKACJA ŁĄCZY SIĘ Z BAZĄ DANYCH: {DATABASE_URL[:30]}... ---")
if not GOOGLE_MAPS_API_KEY:
    print("--- OSTRZEŻENIE: Brak klucza Google Maps API (zmienna 'GOOGLE_MAPS_API_KEY') ---")

# === INICJALIZACJA BAZY DANYCH (ORM) ===
try:
    engine = create_engine(DATABASE_URL, future=True)
    Base = declarative_base()
    SessionLocal = scoped_session(
        sessionmaker(bind=engine, autocommit=False, autoflush=False, expire_on_commit=False, future=True)
    )
    print("--- Połączenie SQLAlchemy zainicjalizowane ---")
except Exception as e:
    print(f"--- BŁĄD Inicjalizacji SQLAlchemy: {e} ---")
    sys.exit(1)  # Wyjście z aplikacji jeśli baza nie działa

# --- KONFIGURACJA GUS (PRODUKCJA) ---
# Wpisz tu Twój klucz, który potwierdziliśmy, że działa
GUS_API_KEY = os.environ.get('GUS_API_KEY', 'fdaad96a2edb4604a8b7')

# --- KONFIGURACJA SMTP (dane wrażliwe TYLKO ze zmiennych środowiskowych .env) ---
SMTP_SERVER = os.environ.get('SMTP_SERVER', "smtp.gmail.com")
SMTP_PORT = int(os.environ.get('SMTP_PORT', 587))
SMTP_USER = os.environ.get('SMTP_USER', "romanlojek@gmail.com")
SMTP_PASSWORD = os.environ.get('SMTP_PASSWORD', '')  # "Hasło aplikacji" Gmail — wpisz do .env
if not SMTP_PASSWORD:
    print("--- OSTRZEŻENIE: Brak SMTP_PASSWORD w .env — automatyczna wysyłka maili będzie się nie udawać ---")


def build_email_message(to_email, subject, html_body):
    """
    Buduje wiadomość z poprawnym kodowaniem nagłówków (RFC 2047).
    EmailMessage automatycznie koduje polskie znaki w Subject — stary MIMEMultipart
    rzucał UnicodeEncodeError przy send_message, więc maile z polskim tematem
    "cicho" nie wychodziły (wyjątek łapał tylko print w except).
    """
    msg = EmailMessage()
    msg['From'] = SMTP_USER
    msg['To'] = to_email
    msg['Subject'] = subject
    msg.set_content("Wiadomość w formacie HTML — wyświetl ją w kliencie poczty obsługującym HTML.")
    msg.add_alternative(html_body, subtype='html')
    return msg


def send_email_sync(to_email, subject, html_body, timeout=30):
    """Wysyła e-mail synchronicznie. Zwraca True przy sukcesie; błąd loguje też do bazy (SystemLog)."""
    server = None
    try:
        msg = build_email_message(to_email, subject, html_body)
        server = smtplib.SMTP(SMTP_SERVER, SMTP_PORT, timeout=timeout)
        server.starttls()
        server.login(SMTP_USER, SMTP_PASSWORD)
        server.send_message(msg)
        print(f"📧 E-mail wysłany do: {to_email}")
        return True
    except Exception as e:
        print(f"❌ Błąd wysyłania e-maila do {to_email}: {e}")
        try:
            log_activity("MAIL_BLAD", f"Do: {to_email} | Temat: {subject} | Błąd: {e}", level="ERROR")
        except Exception:
            pass
        return False
    finally:
        if server is not None:
            try:
                server.quit()
            except Exception:
                pass


def send_email_async(to_email, subject, body):
    """Funkcja pomocnicza wysyłająca e-mail w tle (osobny wątek, nie blokuje UI)."""

    def _send():
        send_email_sync(to_email, subject, body)

    # Uruchomienie w nowym wątku, żeby nie blokować UI
    thread = threading.Thread(target=_send)
    thread.start()


def send_notification(client_email, client_phone, message_type, details):
    """
    Wysyła powiadomienie do klienta.
    message_type: 'created', 'updated', 'deleted'
    details: słownik z datą, godziną, terapeutą
    """
    subject = ""
    body = ""

    if message_type == 'created':
        subject = "Nowa wizyta w Centrum"
        body = f"Zaplanowano wizytę: {details['date']} o {details['time']} u {details['therapist']}."
    elif message_type == 'updated':
        subject = "Zmiana terminu wizyty"
        body = f"Aktualizacja wizyty. Nowy termin: {details['date']} o {details['time']}."
    elif message_type == 'deleted':
        subject = "Odwołanie wizyty"
        body = f"Wizyta w dniu {details['date']} została odwołana."

    # 1. Wysyłka E-mail (jeśli klient ma e-mail)
    if client_email:
        try:
            send_email_async(client_email, subject, body)  # Twoja funkcja z app.py
            print(f"E-mail wysłany do {client_email}")
        except Exception as e:
            print(f"Błąd wysyłki e-mail: {e}")

    # 2. Wysyłka SMS (jeśli klient ma nr telefonu i masz API)
    if client_phone:
        # Tu wstaw kod integracji z SMSAPI / Twilio
        # np. smsapi.send(to=client_phone, message=body)
        print(f"SMS (symulacja) do {client_phone}: {body}")



# ==========================================
# 1. MODEL BAZY DANYCH DLA KOMEND
# ==========================================

class FirmaSettings(Base):
    __tablename__ = "firma_settings"

    id = Column(Integer, primary_key=True)
    firma_id = Column(
        Integer,
        ForeignKey("firma.id", ondelete="CASCADE"),
        nullable=False,
        unique=True,
        index=True,
    )
    journal_reminder_frequency = Column(String(20), default="weekly", nullable=False)
    journal_reminder_weekday = Column(Integer, default=5, nullable=False)
    journal_reminder_hour = Column(Integer, default=9, nullable=False)
    journal_reminder_email_override = Column(String(255), nullable=True)
    last_journal_reminder_sent_at = Column(DateTime(timezone=True), nullable=True)
    updated_at = Column(DateTime(timezone=True), onupdate=func.now())

    firma = relationship("Firma", backref="settings")

    def as_dict(self):
        return {
            "firma_id": self.firma_id,
            "journal_reminder_frequency": self.journal_reminder_frequency,
            "journal_reminder_weekday": self.journal_reminder_weekday,
            "journal_reminder_hour": self.journal_reminder_hour,
            "journal_reminder_email_override": self.journal_reminder_email_override,
            "last_journal_reminder_sent_at": self.last_journal_reminder_sent_at.isoformat() if self.last_journal_reminder_sent_at else None,
        }


class VoiceCommand(Base):
    __tablename__ = 'voice_commands'
    id = Column(Integer, primary_key=True)
    phrases = Column(String, nullable=False) # Oddzielone przecinkami, np. "otwórz kasę, finanse"
    action_type = Column(String, default="navigate") # 'navigate' (link) lub 'click' (kliknięcie przycisku)
    target = Column(String, nullable=False) # Adres URL (np. '/finanse') lub ID przycisku (np. '#zapiszBtn')

class ClientMonthlyLimit(Base):
    __tablename__ = 'client_monthly_limits'

    id = Column(Integer, primary_key=True)
    client_id = Column(Integer, ForeignKey('clients.id'), nullable=False)
    year = Column(Integer, nullable=False)
    month = Column(Integer, nullable=False)
    hours_limit = Column(Integer, default=0)  # Limit w godzinach (np. 8)
    firma_id = Column(Integer, ForeignKey('firma.id', ondelete="CASCADE"),  nullable=False)
    photo_consent = Column(Boolean, default=True)  # Domyślnie zgoda


class BoardResolution(Base):
    __tablename__ = 'board_resolutions'

    id = Column(Integer, primary_key=True)
    title = Column(String(255), nullable=False)  # Numer/Nazwa uchwały
    resolution_date = Column(Date, nullable=False)
    description = Column(Text)
    file_path = Column(String(500))  # Ścieżka do pliku
    file_name = Column(String(255))  # Oryginalna nazwa pliku
    created_at = Column(DateTime(timezone=True), server_default=func.now())
    updated_at = Column(DateTime(timezone=True), onupdate=func.now())
    firma_id = Column(Integer, ForeignKey('firma.id', ondelete="CASCADE"),  nullable=False)

    def as_dict(self):
        return {
            'id': self.id,
            'title': self.title,
            'resolution_date': self.resolution_date.isoformat() if self.resolution_date else None,
            'description': self.description,
            'file_name': self.file_name,
            'has_file': bool(self.file_path),
            'created_at': self.created_at.isoformat() if self.created_at else None
        }


class GusClient:
    """
    Klient do GUS BIR1 (Produkcja).
    POPRAWIONA STRUKTURA XML (Namespaces).
    """
    SERVICE_URL = 'https://wyszukiwarkaregon.stat.gov.pl/wsBIR/UslugaBIRzewnPubl.svc'
    HEADERS = {'Content-Type': 'application/soap+xml; charset=utf-8'}
   

    def __init__(self, api_key):
        self.api_key = api_key
        self.sid = None

    def login(self):
        # Payload logowania (tu namespace jest prosty)
        payload = f"""
        <soap:Envelope xmlns:soap="http://www.w3.org/2003/05/soap-envelope" xmlns:ns="http://CIS/BIR/PUBL/2014/07">
           <soap:Header xmlns:wsa="http://www.w3.org/2005/08/addressing">
              <wsa:To>{self.SERVICE_URL}</wsa:To>
              <wsa:Action>http://CIS/BIR/PUBL/2014/07/IUslugaBIRzewnPubl/Zaloguj</wsa:Action>
           </soap:Header>
           <soap:Body>
              <ns:Zaloguj>
                 <ns:pKluczUzytkownika>{self.api_key}</ns:pKluczUzytkownika>
              </ns:Zaloguj>
           </soap:Body>
        </soap:Envelope>
        """
        try:
            response = requests.post(self.SERVICE_URL, data=payload, headers=self.HEADERS, timeout=20)
            match = re.search(r'<[^>]*ZalogujResult[^>]*>(.*?)</[^>]*ZalogujResult>', response.text)
            if match and match.group(1):
                self.sid = match.group(1)
                return True
            print(f"GUS Login Failed. Body: {response.text[:200]}")
        except Exception as e:
            print(f"GUS Login Exception: {e}")
        return False

    def search(self, number, kind='nip'):
        if not self.sid:
            if not self.login():
                return None

        # === KLUCZOWA POPRAWKA XML ===
        # GUS wymaga specyficznego namespace dla DataContract (dat) w parametrach wyszukiwania

        param_tag = "Nip"
        if kind == 'regon':
            param_tag = "Regon"
        elif kind == 'krs':
            param_tag = "Krs"

        # Zwróć uwagę na xmlns:dat w nagłówku i użycie dat:Nip w ciele
        payload = f"""
        <soap:Envelope xmlns:soap="http://www.w3.org/2003/05/soap-envelope" xmlns:ns="http://CIS/BIR/PUBL/2014/07" xmlns:dat="http://CIS/BIR/PUBL/2014/07/DataContract">
           <soap:Header xmlns:wsa="http://www.w3.org/2005/08/addressing">
              <wsa:To>{self.SERVICE_URL}</wsa:To>
              <wsa:Action>http://CIS/BIR/PUBL/2014/07/IUslugaBIRzewnPubl/DaneSzukajPodmioty</wsa:Action>
           </soap:Header>
           <soap:Body>
              <ns:DaneSzukajPodmioty>
                 <ns:pParametryWyszukiwania>
                    <dat:{param_tag}>{number}</dat:{param_tag}>
                 </ns:pParametryWyszukiwania>
              </ns:DaneSzukajPodmioty>
           </soap:Body>
        </soap:Envelope>
        """

        headers = self.HEADERS.copy()
        headers['sid'] = self.sid

        try:
            response = requests.post(self.SERVICE_URL, data=payload, headers=headers, timeout=30)
            if response.status_code == 200:
                return self._parse_with_regex(response.text)
            else:
                print(f"GUS HTTP Error: {response.status_code}")
                return None
        except Exception as e:
            print(f"GUS Search Exception: {e}")
            return None

    def _parse_with_regex(self, raw_text):
        try:
            # 1. Wyciągamy odpowiedź z koperty
            main_match = re.search(r'<[^>]*DaneSzukajPodmiotyResult[^>]*>(.*?)</[^>]*DaneSzukajPodmiotyResult>',
                                   raw_text, re.DOTALL)

            if not main_match:
                print("DEBUG: Brak tagu DaneSzukajPodmiotyResult w odpowiedzi.")
                return None

            inner_xml = main_match.group(1).strip()

            if not inner_xml:
                print("DEBUG: Pusty wynik wewnątrz Result (GUS nie znalazł NIPu).")
                return None

            # 2. Odkodowanie encji HTML (np. &lt; na <)
            inner_xml = html.unescape(inner_xml)

            # Dodatkowy debug w konsoli
            # print(f"DEBUG XML CONTENT: {inner_xml[:200]}...")

            # 3. Parser wartości (szuka <Nazwa>...</Nazwa> lub <dane:Nazwa>...</dane:Nazwa>)
            def get_tag_value(tag_name, text):
                # Regex szukający tagu otwierającego i zamykającego, ignorujący namespace
                pattern = rf'<[^:>]*:?{tag_name}[^>]*>(.*?)</[^:>]*:?{tag_name}>'
                match = re.search(pattern, text, re.DOTALL | re.IGNORECASE)
                return match.group(1).strip() if match else ''

            nazwa = get_tag_value('Nazwa', inner_xml)

            if not nazwa:
                # Próba ratunkowa dla specyficznych przypadków
                if "ErrorCode" in inner_xml:
                    print("DEBUG: GUS zwrócił błąd biznesowy wewnątrz XML.")
                else:
                    print("DEBUG: XML jest, ale nie znaleziono pola 'Nazwa'.")
                return None

            return {
                'nazwa_pelna': nazwa,
                'nip': get_tag_value('Nip', inner_xml),
                'regon': get_tag_value('Regon', inner_xml),
                'krs': get_tag_value('Krs', inner_xml),
                'wojewodztwo': get_tag_value('Wojewodztwo', inner_xml),
                'powiat': get_tag_value('Powiat', inner_xml),
                'gmina': get_tag_value('Gmina', inner_xml),
                'miejscowosc': get_tag_value('Miejscowosc', inner_xml),
                'kod_pocztowy': get_tag_value('KodPocztowy', inner_xml),
                'ulica': get_tag_value('Ulica', inner_xml),
                'nr_nieruchomosci': get_tag_value('NrNieruchomosci', inner_xml),
                'nr_lokalu': get_tag_value('NrLokalu', inner_xml),
                'typ_podmiotu': get_tag_value('TypPodmiotu', inner_xml),
            }
        except Exception as e:
            print(f"REGEX Parse Critical Error: {e}")
            return None


# === MODUŁ LOGOWANIA (Blueprint) ===
auth_bp = Blueprint('auth', __name__, template_folder='templates')
admin_bp = Blueprint('admin', __name__, template_folder='templates')


# ==============================================================================
# === DEKORATORY DOSTĘPU (MUSZĄ BYĆ ZDEFINIOWANE PRZED ICH UŻYCIEM W ROUTACH) ===
# ==============================================================================

def superadmin_required(view):
    """Dostęp tylko i wyłącznie dla globalnego Super Administratora systemu."""
    @wraps(view)
    @login_required
    def wrapped_view(**kwargs):
        # Sprawdzamy sztywno login 'admin' lub globalną flagę, jeśli ją rozbudujesz
        if not current_user.is_admin or current_user.username != 'admin':
            log_activity("PROBA_NARUSZENIA_SUPERADMINA", f"Użytkownik {current_user.username} próbował wejść do panelu SaaS.", level="WARNING")
            flash('Brak globalnych uprawnień Super Admina (SaaS Provider).', 'danger')
            if request.path.startswith('/api/'):
                return jsonify(message="Super Admin privileges required"), 403
            return redirect(url_for('main_index'))
        return view(**kwargs)
    return wrapped_view

        # 1. Pobieramy ID użytkownika z sesji lub z Flask-Login (current_user)
@app.route('/api/superadmin/companies/<int:company_id>/create-admin', methods=['POST'])
@superadmin_required
def superadmin_create_tenant_admin(company_id):
    """Tworzy konto pierwszego Administratora (właściciela instancji) dla konkretnej firmy."""
    data = request.get_json(force=True) or {}
    username = (data.get('username') or '').strip()
    full_name = (data.get('full_name') or '').strip()
    password = data.get('password')

    if not username or not full_name or not password:
        return jsonify({'error': 'Wszystkie pola (Login, Imię i Nazwisko, Hasło) są wymagane.'}), 400

    if len(password) < 4:
        return jsonify({'error': 'Hasło musi mieć co najmniej 4 znaki.'}), 400

    company_name = ""
    try:
        with session_scope() as db_session:
            # 1. Sprawdzenie czy firma w ogóle istnieje
            company = db_session.get(Firma, company_id)
            if not company:
                return jsonify({'error': 'Podana firma nie istnieje.'}), 404

            # 2. Globalna walidacja unikalności loginu
            existing_user = db_session.query(User).filter_by(username=username).first()
            if existing_user:
                return jsonify({'error': f"Login '{username}' jest już zajęty w systemie przez innego użytkownika."}), 409

            # 3. Tworzenie konta zarządcy dla nowego tenantu
            new_admin = User(
                username=username,
                full_name=full_name,
                is_admin=True,          # Dostaje pełne prawa wewnątrz swojej firmy
                is_secretariat=False,
                firma_id=company_id,    # Sztywne zapięcie do nowej firmy
                permissions=""          # Admin domyślnie ma dostęp do wszystkiego w swoim podmiocie
            )
            new_admin.set_password(password) # Metoda automatycznie hashuje hasło
            
            db_session.add(new_admin)
            db_session.flush()
            company_name = company.nazwa_pelna

        # Wywołujemy logowanie bezpiecznie POZA transakcją bazy danych
        log_activity(
            "SUPERADMIN_CREATE_TENANT_ADMIN", 
            f"Utworzono konto zarządcy '{username}' dla firmy: {company_name} (ID: {company_id})"
        )

        return jsonify({'success': True, 'message': f'Konto administratora {username} zostało pomyślnie utworzone.'}), 201

    except Exception as e:
        print(f"❌ Błąd tworzenia tenant-admina: {e}")
        import traceback
        traceback.print_exc()
        return jsonify({'error': f'Błąd wewnętrzny serwera: {str(e)}'}), 500


        

def login_required(view):
    @functools.wraps(view)
    def wrapped_view(**kwargs):
        # 1. Pobieramy ID użytkownika z sesji lub z Flask-Login (current_user)
        user_id = session.get('user_id')
        if not user_id and current_user and current_user.is_authenticated:
            try:
                user_id = int(current_user.get_id() or current_user.id)
                session['user_id'] = user_id
            except Exception:
                pass

        # 2. Jeśli użytkownik nie jest uwierzytelniony ani w sesji, ani w Flask-Login
        if not user_id and not (current_user and current_user.is_authenticated):
            if request.path.startswith('/api/'):
                return jsonify(message="Authentication required"), 401
            flash('Musisz się zalogować, aby uzyskać dostęp do tej strony.')
            return redirect(url_for('auth.login_page'))

        # 3. Sprawdzenie, czy użytkownik istnieje w bazie danych
        with session_scope() as db_session:
            user = db_session.get(User, user_id) if user_id else None
            if user is None:
                session.clear()
                if request.path.startswith('/api/'):
                    return jsonify(message="User invalid"), 401
                flash('Użytkownik nie istnieje. Zaloguj się ponownie.')
                return redirect(url_for('auth.login_page'))

        return view(**kwargs)
    return wrapped_view


def admin_required(view):
    @functools.wraps(view)
    @login_required
    def wrapped_view(**kwargs):
        user_id = session.get('user_id') or (current_user.id if current_user and current_user.is_authenticated else None)
        with session_scope() as db_session:
            user = db_session.get(User, user_id) if user_id else None
            if not user or not user.is_admin:
                if request.path.startswith('/api/'):
                    return jsonify(message="Admin privileges required"), 403
                flash('Nie masz uprawnień administratora, aby uzyskać dostęp do tej strony.')
                return redirect(url_for('main_index'))
        return view(**kwargs)
    return wrapped_view






# Funkcja generująca bezpieczne, losowe hasło
def generate_random_password(length=12):
    alphabet = string.ascii_letters + string.digits + "!@#$%"
    password = ''.join(secrets.choice(alphabet) for i in range(length))
    return password


@admin_bp.route('/api/admin/mass-password-reset', methods=['POST'])
@admin_required
def mass_password_reset_api():
    """Resetuje hasła i generuje CSV z linkiem do logowania."""

    EXCLUDED_USERNAMES = ['admin', 'root', 'administrator', 'support']
    EXCLUDED_IDS = [1]

    # Pobieramy dynamicznie adres strony (np. http://localhost:5000/ lub https://twoja-domena.pl/)
    # Jeśli chcesz konkretny adres, wpisz go w cudzysłowie: SITE_URL = "https://mojafirma.pl/login"
    SITE_URL = request.host_url.rstrip('/') + "/login"

    output = io.StringIO()
    writer = csv.writer(output)

    # === ZMIANA 1: Nowy nagłówek CSV z adresem strony ===
    writer.writerow(['ID', 'Imie i Nazwisko', 'Adres Strony', 'Login', 'Nowe Haslo'])

    try:
        with session_scope() as db_session:
            users = db_session.query(User).all()
            count = 0

            for u in users:
                if u.username in EXCLUDED_USERNAMES or u.id in EXCLUDED_IDS:
                    continue

                new_plain_password = generate_random_password(12)
                u.set_password(new_plain_password)

                display_name = u.full_name if u.full_name else "Brak nazwy"

                # === ZMIANA 2: Dodanie SITE_URL do wiersza ===
                writer.writerow([u.id, display_name, SITE_URL, u.username, new_plain_password])

                count += 1

            output.seek(0)

            return Response(
                output.getvalue(),
                mimetype="text/csv",
                headers={"Content-disposition": "attachment; filename=dane_logowania_users.csv"}
            )

    except Exception as e:
        print(f"Błąd: {e}")
        return jsonify({'error': str(e)}), 500


# --- ENDPOINT: MASOWY RESET + WYSYŁKA SMTP ---

@app.route('/api/superadmin/companies', methods=['GET'])
@superadmin_required
def superadmin_get_all_companies():
    """Zwraca globalną listę wszystkich firm wraz z ich statystykami użycia."""
    try:
        with SessionLocal() as s:
            # 1. Pobieramy wszystkie firmy
            firmy = s.query(Firma).order_by(Firma.id).all()
            
            # 2. Pobieramy statystyki per firma (cross-tenant counts)
            # Liczymy ile zasobów ma przypisane dane firma_id
            stats_users = dict(s.query(User.firma_id, func.count(User.id)).group_by(User.firma_id).all())
            stats_clients = dict(s.query(Client.firma_id, func.count(Client.id)).group_by(Client.firma_id).all())
            stats_therapists = dict(s.query(Therapist.firma_id, func.count(Therapist.id)).group_by(Therapist.firma_id).all())
            stats_journal = dict(s.query(JournalEntry.firma_id, func.count(JournalEntry.id)).group_by(JournalEntry.firma_id).all())

            results = []
            for f in firmy:
                company_data = f.as_dict()
                # Doklejamy statystyki systemowe
                company_data['stats'] = {
                    'users_count': stats_users.get(f.id, 0),
                    'clients_count': stats_clients.get(f.id, 0),
                    'therapists_count': stats_therapists.get(f.id, 0),
                    'journal_entries_count': stats_journal.get(f.id, 0)
                }
                results.append(company_data)
                
            return jsonify(results), 200
    except Exception as e:
        print(f"❌ Błąd SuperAdmin API (GET): {e}")
        return jsonify({'error': str(e)}), 500


@app.route('/api/superadmin/companies', methods=['POST'])
@superadmin_required
def superadmin_create_company():
    """Tworzy nowy podmiot (nowego klienta biznesowego / fundację) w systemie."""
    data = request.get_json(force=True) or {}
    
    if not data.get('nazwa_pelna') or not data.get('nip'):
        return jsonify({'error': 'Nazwa pełna i NIP są absolutnie wymagane.'}), 400

    try:
        # KROK 1: Przygotowujemy czyste, bezpieczne zmienne Pythona poza bazą danych
        saved_id = None
        saved_name = ""

        # KROK 2: Używamy Twojego zunifikowanego managera sesji: session_scope
        with session_scope() as db_session:
            # Sprawdzenie duplikatu NIP w skali CAŁEGO systemu
            existing = db_session.query(Firma).filter_by(nip=data['nip'].strip()).first()
            if existing:
                return jsonify({'error': f"Firma z NIP {data['nip']} już istnieje w systemie (ID: {existing.id})."}), 409

            typ_enum = TypPodmiotuEnum[data.get('typ', 'fundacja')]

            nowa_firma = Firma(
                typ=typ_enum,
                nazwa_pelna=data['nazwa_pelna'].strip(),
                nazwa_skrocona=data.get('nazwa_skrocona', '').strip() or None,
                nip=data['nip'].strip(),
                regon=data.get('regon', '').strip() or None,
                krs=data.get('krs', '').strip() or None,
                ulica=data.get('ulica', '').strip() or None,
                numer_budynku=data.get('numer_budynku', '').strip() or None,
                kod_pocztowy=data.get('kod_pocztowy', '00-000').strip(),
                miasto=data.get('miasto', 'Warszawa').strip(),
                email=data.get('email', '').strip() or None,
                telefon=data.get('telefon', '').strip() or None,
                zarzad=data.get('zarzad', '').strip() or None
            )
            db_session.add(nowa_firma)
            db_session.flush()  # Wymuszamy nadanie ID przez PostgreSQL
            
            # KROK 3: Robimy szybką migawkę wartości do zmiennych lokalnych
            saved_id = nowa_firma.id
            saved_name = nowa_firma.nazwa_pelna

        # KROK 4: Wywołujemy logowanie bezpiecznie POZA blokiem transakcji bazy,
        # podając czyste zmienne tekstowe/liczbowe, a nie obiekty ORM
        log_activity("SUPERADMIN_CREATE_COMPANY", f"Utworzono nową firmę: {saved_name} (ID: {saved_id})")
        
        return jsonify({'success': True, 'company_id': saved_id}), 201
    except Exception as e:
        print(f"❌ Błąd SuperAdmin API (POST): {e}")
        return jsonify({'error': str(e)}), 500
        
@app.route('/api/superadmin/companies/<int:company_id>', methods=['DELETE'])
@superadmin_required
def superadmin_delete_company(company_id):
    if company_id == 2:
        return jsonify({'error': 'Nie możesz usunąć głównej, produkcyjnej fundacji (ID: 2).'}), 400

    try:
        saved_name = ""
        with session_scope() as db_session:
            firma = db_session.get(Firma, company_id)
            if not firma:
                return jsonify({'error': 'Podmiot nie istnieje.'}), 404

            saved_name = firma.nazwa_pelna
            db_session.delete(firma)
            
        # Logowanie wywołane bezpiecznie po zatwierdzeniu usunięcia w bazie
        log_activity("SUPERADMIN_DELETE_COMPANY", f"TRWAŁE USUNIĘCIE FIRMY: {saved_name} (ID: {company_id})", level="WARNING")
        return jsonify({'success': True, 'message': f'Firma {saved_name} została trwale usunięta.'}), 200
    except Exception as e:
        return jsonify({'error': str(e)}), 500
        
@app.route('/api/debug/smtp-test', methods=['GET'])
@admin_required
def smtp_test():
    """
    Testuje połączenie i logowanie do SMTP (bez wysyłki maila).
    Opcjonalnie ?send=1 — wysyła dodatkowo testowy e-mail na adres SMTP_USER.
    """
    try:
        server = smtplib.SMTP(SMTP_SERVER, SMTP_PORT, timeout=15)
        server.starttls()
        server.login(SMTP_USER, SMTP_PASSWORD)
        server.quit()
    except Exception as e:
        log_activity("SMTP_TEST", f"FAIL: {e}", level="ERROR")
        return jsonify({'ok': False, 'error': str(e)}), 500

    result = {'ok': True, 'message': f'Logowanie do {SMTP_SERVER}:{SMTP_PORT} jako {SMTP_USER} działa.'}
    if request.args.get('send') == '1':
        result['test_mail_sent'] = send_email_sync(
            SMTP_USER, "Test SMTP — system Centrum",
            "<p>To jest testowa wiadomość SMTP. Jeśli ją dostałeś, automatyczna wysyłka maili działa.</p>"
        )
    log_activity("SMTP_TEST", "OK" + (" (z wysyłką testową)" if request.args.get('send') == '1' else ""))
    return jsonify(result), 200


@app.route('/api/admin/mass-password-reset-email', methods=['POST'])
@admin_required
def mass_password_reset_email_api():
    EXCLUDED_USERNAMES = ['admin', 'root', 'administrator']
    SITE_URL = request.host_url.rstrip('/') + "/login"

    # Statystyki dla Frontendu
    stats = {'sent': 0, 'failed': 0, 'skipped': 0, 'no_email': 0}
    server = None

    try:
        with session_scope() as db_session:
            users = db_session.query(User).all()

            # 1. Otwieramy połączenie z Gmailem RAZ (dla wydajności).
            #    UWAGA: błąd logowania musi RZUCIĆ wyjątek — dawniej był tu 'return'
            #    wewnątrz session_scope, co wykonywało COMMIT i resetowało hasła
            #    w bazie mimo że żaden mail nie został wysłany.
            server = smtplib.SMTP(SMTP_SERVER, SMTP_PORT, timeout=30)
            server.starttls()
            server.login(SMTP_USER, SMTP_PASSWORD)

            # 2. Pętla po użytkownikach
            for u in users:
                # Pomijanie adminów
                if u.username in EXCLUDED_USERNAMES:
                    stats['skipped'] += 1
                    continue

                # Sprawdzenie czy user ma email
                user_email = getattr(u, 'email', None)  # Zakładam, że pole w bazie to 'email'
                if not user_email or '@' not in user_email:
                    stats['no_email'] += 1
                    continue

                # Generowanie i zapis hasła
                new_plain_password = generate_random_password(12)
                u.set_password(new_plain_password)

                # 3. Tworzenie wiadomości Email
                subject = f"Dostępy do systemu - {u.full_name}"

                # Treść HTML (ładniejsza)
                html_body = f"""
                <html>
                  <body>
                    <h2>Witaj {u.full_name},</h2>
                    <p>Twoje hasło do systemu zostało zresetowane przez administratora.</p>
                    <hr>
                    <p><strong>Strona:</strong> <a href="{SITE_URL}">{SITE_URL}</a></p>
                    <p><strong>Login:</strong> {u.username}</p>
                    <p><strong>Hasło:</strong> <span style="background-color: #eee; padding: 5px; font-family: monospace; font-weight: bold;">{new_plain_password}</span></p>
                    <hr>
                    <p><small>Wiadomość wygenerowana automatycznie.</small></p>
                  </body>
                </html>
                """

                msg = build_email_message(user_email, subject, html_body)

                # 4. Wysyłka
                try:
                    server.send_message(msg)
                    stats['sent'] += 1
                    print(f"✅ Wysłano do: {user_email}")
                except Exception as e:
                    print(f"❌ Błąd wysyłki do {u.username}: {e}")
                    stats['failed'] += 1

            # 5. Commit dzieje się automatycznie przy wyjściu z session_scope
            return jsonify({
                'message': 'Proces zakończony.',
                'stats': stats
            })

    except Exception as e:
        print(f"Błąd krytyczny: {e}")
        return jsonify({'error': str(e)}), 500
    finally:
        # Połączenie SMTP zamykamy ZAWSZE (także przy błędzie) — wcześniej przy błędzie zostawało otwarte
        if server is not None:
            try:
                server.quit()
            except Exception:
                pass


# W pliku app.py (lub tam, gdzie są dekoratory)
# W pliku app.py
# Wewnątrz class User(Base, UserMixin):

def has_permission(self, module_name):
    """Sprawdza czy użytkownik ma dostęp do danego modułu."""
    # 1. Admin ma dostęp do wszystkiego
    if self.is_admin:
        return True

    # 2. Jeśli brak uprawnień
    if not self.permissions:
        return False

    # 3. Rozdzielamy po przecinku i USUWAMY SPACJE (strip)
    # To naprawia problem "clients, drivers" vs "clients,drivers"
    perms = [p.strip() for p in self.permissions.split(',')]

    return module_name in perms


@admin_bp.route('/admin/change-password', methods=['GET'])
@admin_required  # Wymaga zalogowania i uprawnień admina
def admin_change_password_page():
    """Wyświetla stronę do zmiany hasła."""
    return render_template('change_password.html')


@admin_bp.route('/admin/zarzadzaj-firma', methods=['GET'])
@admin_required
def zarzadzaj_firma_page():
    """Wyświetla stronę do zarządzania firmami/fundacjami."""
    return render_template('zarzadzaj_firma.html')


@admin_bp.route('/admin/edit-user', methods=['GET'])
@admin_required
def admin_edit_user_page():
    """Wyświetla stronę do edycji danych i ról użytkownika."""
    # Upewnij się, że używasz poprawnej nazwy pliku HTML
    return render_template('user_update.html')


@admin_bp.route('/api/admin/reset-user-password', methods=['POST'])
@admin_required  # Wymaga zalogowania i uprawnień admina
def handle_admin_reset_user_password():
    """
    Obsługuje żądanie resetowania hasła DLA INNEGO użytkownika przez administratora.
    Oczekuje na user_id oraz new_password w ciele żądania.
    """
    # ID administratora wykonującego akcję (zalogowanego użytkownika)
    admin_id = session.get('user_id')

    data = request.get_json()
    user_id_to_reset = data.get('user_id')  # ID użytkownika, którego hasło zmieniamy
    new_password = data.get('new_password')

    # 1. Walidacja danych wejściowych
    if not user_id_to_reset or not new_password:
        return jsonify({'error': 'Wymagane są: ID użytkownika i nowe hasło.'}), 400

    # Upewnij się, że user_id jest liczbą całkowitą
    try:
        user_id_to_reset = int(user_id_to_reset)
    except ValueError:
        return jsonify({'error': 'Nieprawidłowy format ID użytkownika.'}), 400

    if len(new_password) < 4:
        return jsonify({'error': 'Nowe hasło musi mieć co najmniej 4 znaki.'}), 400

    # 2. Zapobieganie przypadkowemu resetowi własnego hasła przez ten endpoint
    # (powinien być użyty oddzielny endpoint do zmiany własnego hasła)
    # Możesz dodać logikę, aby admin nie mógł zresetować hasła innego superadmina, jeśli taka polityka jest wymagana.
    # if user_id_to_reset == admin_id:
    #     return jsonify({'error': 'Użyj formularza "Zmień własne hasło" do zmiany własnego hasła.'}), 403

    try:
        with session_scope() as db_session:
            # 3. Znajdź użytkownika DOCELOWEGO w bazie
            user_to_update = db_session.get(User, user_id_to_reset)

            if not user_to_update:
                return jsonify({'error': f'Użytkownik o ID {user_id_to_reset} nie znaleziony.'}), 404

            # 4. Ustaw nowe hasło (metoda set_password automatycznie hashuje)
            user_to_update.set_password(new_password)
            # session_scope() zrobi commit automatycznie

            # 5. Logowanie akcji
            admin_user = db_session.get(User, admin_id)
            admin_username = admin_user.username if admin_user else "Nieznany Admin"
            print(
                f"Admin '{admin_username}' (ID: {admin_id}) zresetował hasło użytkownika '{user_to_update.username}' (ID: {user_id_to_reset}).")

            flash(f'Hasło użytkownika {user_to_update.username} zostało pomyślnie zresetowane.', 'success')
            return jsonify(
                {'message': f'Hasło użytkownika {user_to_update.username} zostało zresetowane pomyślnie.'}), 200

    except Exception as e:
        # session_scope() zrobi rollback automatycznie
        print(f"Błąd podczas resetowania hasła przez Admina (ID: {admin_id}) dla user_id={user_id_to_reset}: {str(e)}")
        import traceback
        traceback.print_exc()
        return jsonify({'error': f'Wystąpił błąd serwera: {str(e)}'}), 500


# W app.py


@admin_bp.route('/admin/manage-users', methods=['GET'])
@admin_required
def manage_users_page():
    """Wyświetla stronę panelu zarządzania użytkownikami i rolami."""  # <-- 4 spacje wcięcia
    try:  # <-- 4 spacje wcięcia
        with session_scope() as db_session:  # <-- 8 spacji wcięcia
            all_users = db_session.query(User).order_by(User.username).all()
            all_therapists = db_session.query(Therapist).filter_by(active=True).order_by(Therapist.full_name).all()
            all_drivers = db_session.query(Driver).filter_by(active=True).order_by(Driver.full_name).all()

            # return render_template musi być WEWNĄTRZ bloku 'with'
            return render_template(  # <-- 12 spacji wcięcia
                'manage_users.html',
                users=all_users,
                therapists=all_therapists,
                drivers=all_drivers
            )
    except Exception as e:  # <-- 4 spacje wcięcia
        print(f"Błąd podczas ładowania strony zarządzania użytkownikami: {e}")
        traceback.print_exc()
        flash(f"Wystąpił błąd podczas ładowania strony: {e}", "danger")
        return redirect(url_for('main_index'))


@admin_bp.route('/api/firma/<int:id>', methods=['PUT'])
@admin_required
def update_firma(id):
    data = request.json

    # Funkcja pomocnicza (taka sama jak w handle_update_firma)
    def clean_empty(value):
        if isinstance(value, str) and not value.strip():
            return None
        if not value:
            return None
        return value

    try:
        with session_scope() as db_session:
            firma = db_session.query(Firma).get(id)
            if not firma:
                return jsonify({'error': 'Firma nie znaleziona'}), 404

            # Aktualizacja pól
            firma.nazwa_pelna = data.get('nazwa_pelna', firma.nazwa_pelna)
            firma.nazwa_skrocona = data.get('nazwa_skrocona', firma.nazwa_skrocona)
            firma.nip = data.get('nip', firma.nip)

            # Pola z clean_empty
            firma.regon = clean_empty(data.get('regon'))
            firma.krs = clean_empty(data.get('krs'))
            firma.email = clean_empty(data.get('email'))

            firma.ulica = data.get('ulica', firma.ulica)
            firma.numer_budynku = data.get('numer_budynku', firma.numer_budynku)
            firma.numer_lokalu = data.get('numer_lokalu', firma.numer_lokalu)
            firma.kod_pocztowy = data.get('kod_pocztowy', firma.kod_pocztowy)
            firma.miasto = data.get('miasto', firma.miasto)
            firma.telefon = data.get('telefon', firma.telefon)
            firma.strona_www = data.get('strona_www', firma.strona_www)
            firma.adres_dodatkowy_ulica = data.get('adres_dodatkowy_ulica', firma.adres_dodatkowy_ulica)
            firma.adres_dodatkowy_numer = data.get('adres_dodatkowy_numer', firma.adres_dodatkowy_numer)
            firma.adres_dodatkowy_kod = data.get('adres_dodatkowy_kod', firma.adres_dodatkowy_kod)
            firma.adres_dodatkowy_miasto = data.get('adres_dodatkowy_miasto', firma.adres_dodatkowy_miasto)

            # Typ (Enum)
            if 'typ' in data:
                try:
                    firma.typ = TypPodmiotuEnum[data['typ']]
                except KeyError:
                    pass

            # --- NOWE POLA ---
            # Logika dla zarządu (lista -> string)
            raw_zarzad = data.get('zarzad')
            if isinstance(raw_zarzad, list):
                firma.zarzad = "\n".join([str(x) for x in raw_zarzad if x])
            else:
                firma.zarzad = raw_zarzad

            # Logika dla PKD (lista -> string)
            raw_pkd = data.get('pkd')
            if isinstance(raw_pkd, list):
                firma.pkd = ", ".join([str(x) for x in raw_pkd if x])
            else:
                firma.pkd = raw_pkd

            # Cele
            raw_cele = data.get('cele_statutowe')
            if isinstance(raw_cele, list):
                firma.cele_statutowe = "\n".join([str(x) for x in raw_cele if x])
            else:
                firma.cele_statutowe = raw_cele

            # session_scope() automatycznie zrobi commit
            return jsonify({'message': 'Dane zaktualizowane', 'id': firma.id}), 200

    except Exception as e:
        print(f"Błąd edycji firmy: {e}")
        import traceback
        traceback.print_exc()
        return jsonify({'error': str(e)}), 500






@admin_bp.route('/api/podmiot/szukaj-krs/<string:numer_krs>', methods=['GET'])
@login_required
def handle_szukaj_krs(numer_krs):
    """Pobiera dane z oficjalnego API Ministerstwa Sprawiedliwości (MS Gov)."""

    print(f"--> Szukam KRS: {numer_krs} w API MS Gov...")

    if not numer_krs or len(numer_krs) != 10 or not numer_krs.isdigit():
        return jsonify({'error': 'Nieprawidłowy numer KRS (wymagane 10 cyfr)'}), 400

    # API MS wymaga podania rejestru: 'P' (Przedsiębiorcy) lub 'S' (Stowarzyszenia/Fundacje).
    # Sprawdzamy oba, bo nie wiemy czym jest podmiot.
    rejestry_do_sprawdzenia = ['S', 'P']
    data = None

    for rej in rejestry_do_sprawdzenia:
        url = f"https://api-krs.ms.gov.pl/api/krs/OdpisAktualny/{numer_krs}?rejestr={rej}&format=json"
        try:
            # verify=False jest konieczne dla MS Gov w Pythonie
            response = requests.get(url, verify=False, timeout=10)
            if response.status_code == 200:
                data = response.json()
                break  # Znaleziono!
        except Exception as e:
            print(f"Błąd przy sprawdzaniu rejestru {rej}: {e}")
            continue

    if not data:
        return jsonify({'error': 'Nie znaleziono podmiotu w KRS (lub błąd połączenia z MS)'}), 404

    try:

        # --- PARSOWANIE JSON z MS GOV ---
        odpis = data.get('odpis', {})
        dane = odpis.get('dane', {})

        # 1. Dane podstawowe
        dzial1 = dane.get('dzial1', {})
        dane_podmiotu = dzial1.get('danePodmiotu', {})
        siedziba = dzial1.get('siedzibaIAdres', {}).get('adres', {})

        nazwa = dane_podmiotu.get('nazwa', '').replace('"', '')
        forma_prawna = dane_podmiotu.get('formaPrawna', '')

        # 2. Adres
        ulica = siedziba.get('ulica', '')
        nr_domu = siedziba.get('nrDomu', '')
        nr_lokalu = siedziba.get('nrLokalu', '')
        miejscowosc = siedziba.get('miejscowosc', '')
        kod_pocztowy = siedziba.get('kodPocztowy', '')

        # 3. NIP i REGON
        identyfikatory = dane_podmiotu.get('identyfikatory', {})
        nip = identyfikatory.get('nip', '')
        regon = identyfikatory.get('regon', '')

        # 4. Zarząd (Dział 2 - Reprezentacja)
        zarzad_lista = []

        # Pobieramy dział 2
        dzial2 = dane.get('dzial2', {})

        # Szukamy organu reprezentacji (dla spółek/fundacji)
        reprezentacja = dzial2.get('reprezentacja', {})
        sklad = reprezentacja.get('sklad', [])

        # Czasami organ nadzoru jest ważniejszy, ale zazwyczaj szukamy zarządu.
        # Jeśli 'sklad' to nie lista (tylko pojedynczy obiekt), pakujemy go w listę
        if isinstance(sklad, dict):
            sklad = [sklad]

        if sklad:
            for osoba in sklad:
                # API MS zwraca: "nazwisko": { "nazwiskoI": "KOWALSKI" }
                # Musimy wejść głębiej w strukturę:

                # 1. Pobieramy nazwisko
                n_obj = osoba.get('nazwisko', {})
                nazwisko = n_obj.get('nazwiskoI', '') if isinstance(n_obj, dict) else str(n_obj)

                # 2. Pobieramy imię
                i_obj = osoba.get('imiona', {})
                imie = i_obj.get('imie', '') if isinstance(i_obj, dict) else str(i_obj)

                # 3. Pobieramy funkcję
                funkcja = osoba.get('funkcjaWOrganie', 'Członek organu')

                # 4. Formatowanie (opcjonalne): Zmiana "JAN KOWALSKI" na "Jan Kowalski"
                # Używamy .title(), żeby wyglądało ładniej w raporcie
                if nazwisko or imie:
                    pelne_imie = f"{imie} {nazwisko}".strip().title()
                    # .title() zamienia 'JAN' na 'Jan'

                    # Sklejamy w jeden ciąg
                    wpis = f"{pelne_imie} - {funkcja}"
                    zarzad_lista.append(wpis)

        # 5. Cele Statutowe (Dział 3)
        dzial3 = dane.get('dzial3', {})
        cele_statutowe = ""

        # Cel działania (często występuje u fundacji)
        cel_obj = dzial3.get('celDzialaniaOrganizacji', {})
        if cel_obj and cel_obj.get('celDzialania'):
            cele_raw = cel_obj.get('celDzialania', [])
            if isinstance(cele_raw, list):
                # Łączymy cele, usuwając numery np. "1. Cel..."
                cele_statutowe = " ".join([c.get('cel', '') for c in cele_raw])
            elif isinstance(cele_raw, str):
                cele_statutowe = cele_raw

        # Jeśli puste, sprawdź przedmiot działalności (dla firm)
        pkd_lista = []
        przedmiot = dzial3.get('przedmiotDzialalnosci', {})
        pkd_raw = przedmiot.get('przedmiotPrzewazajacejDzialalnosci', [])

        # Parsowanie PKD
        if isinstance(pkd_raw, list):
            for p in pkd_raw:
                pkd_lista.append(p.get('kodDzial', '') + p.get('kodKlasa', '') + p.get('kodPodklasa', ''))
        elif isinstance(pkd_raw, dict):  # Czasem to jeden obiekt
            pkd_lista.append(pkd_raw.get('kodDzial', '') + pkd_raw.get('kodKlasa', '') + pkd_raw.get('kodPodklasa', ''))

        # Wykrywanie typu
        typ_frontend = 'firma'
        upper_nazwa = nazwa.upper()
        if 'FUNDACJA' in upper_nazwa:
            typ_frontend = 'fundacja'
        elif 'STOWARZYSZENIE' in upper_nazwa or 'OSP ' in upper_nazwa:
            typ_frontend = 'stowarzyszenie'

        # Budowanie odpowiedzi
        wynik = {
            'typ': typ_frontend,
            'nazwa_pelna': nazwa,
            'nazwa_skrocona': nazwa,
            'nip': nip,
            'regon': regon,
            'krs': numer_krs,

            'miasto': miejscowosc,
            'ulica': ulica,
            'numer_budynku': nr_domu,
            'numer_lokalu': nr_lokalu,
            'kod_pocztowy': kod_pocztowy,
            'email': '',

            'zarzad': zarzad_lista,  # To trafi do pola Zarząd
            'cele_statutowe': cele_statutowe,  # To trafi do pola Cele
            'pkd': pkd_lista
        }

        return jsonify(wynik)

    except Exception as e:
        print(f"Błąd parsowania API MS: {e}")
        import traceback
        traceback.print_exc()
        return jsonify({'error': 'Błąd przetwarzania danych z rejestru'}), 500


@admin_bp.route('/api/firma', methods=['POST'])
@admin_required
def handle_create_firma():
    """API Endpoint do tworzenia nowej firmy lub fundacji."""
    data = request.get_json()
    if not data:
        return jsonify({'error': 'Brak danych JSON'}), 400

    # Podstawowa walidacja
    required_fields = ['nazwa_pelna', 'typ', 'nip', 'kod_pocztowy', 'miasto']
    missing = [f for f in required_fields if not data.get(f)]
    if missing:
        return jsonify({'error': f"Brakujące pola: {', '.join(missing)}"}), 400

    # Sprawdzenie poprawności typu ENUM
    try:
        typ_enum = TypPodmiotuEnum[data['typ']]
    except KeyError:
        return jsonify({'error': f"Nieprawidłowy typ podmiotu: {data['typ']}"}), 400

    # --- FUNKCJA POMOCNICZA DO CZYSZCZENIA PUSTYCH STRINGÓW ---
    def clean_empty(value):
        if value and isinstance(value, str) and value.strip() == "":
            return None
        return value if value else None

    # --- NOWA LOGIKA: PRZETWARZANIE LIST NA TEKST ---
    # Frontend może przysłać tablicę (z KRS) lub string (wpisany ręcznie)

    # 1. Zarząd (łączymy nową linią)
    raw_zarzad = data.get('zarzad')
    final_zarzad = None
    if isinstance(raw_zarzad, list):
        final_zarzad = "\n".join([str(x) for x in raw_zarzad if x])
    else:
        final_zarzad = raw_zarzad

    # 2. PKD (łączymy przecinkami)
    raw_pkd = data.get('pkd')
    final_pkd = None
    if isinstance(raw_pkd, list):
        final_pkd = ", ".join([str(x) for x in raw_pkd if x])
    else:
        final_pkd = raw_pkd

    # ----------------------------------------------------------

    try:
        with session_scope() as db_session:
            # 1. Sprawdź, czy NIP już istnieje
            existing = db_session.query(Firma).filter_by(nip=data['nip']).first()
            if existing:
                return jsonify({'error': f"Podmiot o numerze NIP {data['nip']} już istnieje w bazie."}), 409

            # 2. Tworzenie obiektu
            nowa_firma = Firma(
                typ=typ_enum,
                nazwa_pelna=data['nazwa_pelna'],
                nazwa_skrocona=data.get('nazwa_skrocona'),
                nip=data['nip'],

                # Pola unique (KRS, REGON, Email) - muszą być NULL jeśli puste
                regon=clean_empty(data.get('regon')),
                krs=clean_empty(data.get('krs')),
                email=clean_empty(data.get('email')),

                ulica=data.get('ulica'),
                numer_budynku=data.get('numer_budynku'),
                numer_lokalu=data.get('numer_lokalu'),
                kod_pocztowy=data['kod_pocztowy'],
                miasto=data['miasto'],
                kraj=data.get('kraj', 'Polska'),
                telefon=data.get('telefon'),
                strona_www=data.get('strona_www'),
                adres_dodatkowy_ulica=data.get('adres_dodatkowy_ulica'),
                adres_dodatkowy_numer=data.get('adres_dodatkowy_numer'),
                adres_dodatkowy_kod=data.get('adres_dodatkowy_kod'),
                adres_dodatkowy_miasto=data.get('adres_dodatkowy_miasto'),

                # --- TUTAJ DODAJEMY NOWE DANE ---
                zarzad=final_zarzad,
                cele_statutowe=data.get('cele_statutowe'),  # To zazwyczaj przychodzi jako string
                pkd=final_pkd
            )

            db_session.add(nowa_firma)
            db_session.flush()

            print(f"Admin '{session.get('username')}' dodał nową firmę: {nowa_firma.nazwa_pelna} (ID: {nowa_firma.id})")
            return jsonify(nowa_firma.as_dict()), 201

    except IntegrityError as e:
        print(f"Błąd IntegrityError przy dodawaniu firmy: {e}")
        err_msg = str(e.orig).lower()
        if 'nip' in err_msg:
            msg = 'Podmiot z tym numerem NIP już istnieje.'
        elif 'regon' in err_msg:
            msg = 'Podmiot z tym numerem REGON już istnieje.'
        elif 'krs' in err_msg:
            msg = 'Podmiot z tym numerem KRS już istnieje.'
        elif 'email' in err_msg:
            msg = 'Ten adres e-mail jest już przypisany do innej firmy.'
        else:
            msg = 'Błąd duplikatu danych (NIP, REGON, KRS lub Email).'

        return jsonify({'error': msg, 'details': str(e.orig)}), 409

    except Exception as e:
        print(f"Nieoczekiwany błąd przy dodawaniu firmy: {e}")
        import traceback
        traceback.print_exc()
        return jsonify({'error': f'Wystąpił błąd serwera: {str(e)}'}), 500


@admin_bp.route('/api/podmiot/szukaj-nip/<nip_numer>', methods=['GET'])
@login_required
def szukaj_w_gus(nip_numer):
    nip_czysty = re.sub(r'[^0-9]', '', nip_numer)
    if len(nip_czysty) != 10:
        return jsonify({'error': 'Nieprawidłowy format NIP.'}), 400

    print(f"--- Szukam NIP: {nip_czysty} ---")

    try:
        # Używamy nowej klasy
        client = GusClient(GUS_API_KEY)
        dane = client.search(nip_czysty)

        if not dane:
            # Ważne: 404 to nie 500. To informacja dla frontendu "nie znaleziono".
            return jsonify({'error': 'Nie znaleziono danych w GUS (lub pusty wynik).'}), 404

        # Logika dla braku ulicy
        ulica = dane.get('ulica', '')
        if not ulica:
            ulica = dane.get('miejscowosc', '')

        wynik = {
            'nazwa_pelna': dane.get('nazwa_pelna', ''),
            'nip': dane.get('nip', ''),
            'regon': dane.get('regon', ''),
            'krs': dane.get('krs', ''),
            'ulica': ulica,
            'numer_budynku': dane.get('nr_nieruchomosci', ''),
            'numer_lokalu': dane.get('nr_lokalu', ''),
            'kod_pocztowy': dane.get('kod_pocztowy', ''),
            'miasto': dane.get('miejscowosc', '')
        }
        return jsonify(wynik), 200

    except Exception as e:
        # Łapiemy absolutnie wszystko i zwracamy jako tekst
        error_msg = f"CRITICAL ERROR: {str(e)}"
        print(error_msg)
        import traceback
        traceback.print_exc()
        # Zwracamy kod 500, ale z treścią błędu w JSON
        return jsonify({'error': error_msg}), 500


@app.route('/api/firma', methods=['GET'])
@login_required
def handle_get_firmy():
    """Zwraca wyłącznie dane firmy przypisanej do sesji użytkownika (Tenant Lock)."""
    current_firma_id = session.get('firma_id', 1)
    try:
        with session_scope() as db_session:
            # Rygorystyczna blokada: zamiast pobierać .all(), pobieramy tylko swoją firmę
            firmy = db_session.query(Firma).filter(Firma.id == current_firma_id).all()
            return jsonify([f.as_dict() for f in firmy]), 200
    except Exception as e:
        return jsonify({'error': str(e)}), 500


@app.route('/api/utils/geocode-clients', methods=['POST'])
@login_required
def geocode_clients():
    import time as sys_time
    from geopy.geocoders import Nominatim

    print("--> Rozpoczynam geokodowanie klientów...")

    try:
        geolocator = Nominatim(user_agent="planer_masowy_fundacji_v2")
        updated_count = 0
        missing_address_list = []  # Lista klientów bez adresu

        with session_scope() as session:
            # Pobieramy klientów bez współrzędnych
            clients = session.query(Client).filter(Client.latitude.is_(None)).limit(10).all()

            if not clients:
                return jsonify({"message": "Wszyscy mają współrzędne.", "updated": 0, "missing_clients": []})

            for client in clients:
                # WALIDACJA ADRESU
                if not client.address or len(client.address.strip()) < 3:
                    # Dodajemy do listy "do poprawy"
                    missing_address_list.append({
                        "id": client.id,
                        "name": client.full_name
                    })
                    continue

                try:
                    query_address = client.address
                    if "Warszawa" not in query_address and "Polska" not in query_address:
                        query_address += ", Warszawa"

                    location = geolocator.geocode(query_address, timeout=10)

                    if location:
                        client.latitude = location.latitude
                        client.longitude = location.longitude
                        updated_count += 1

                    sys_time.sleep(1.1)
                except Exception as e:
                    print(f"Błąd api: {e}")

        return jsonify({
            "updated": updated_count,
            "message": f"Zaktualizowano {updated_count} klientów.",
            "missing_clients": missing_address_list  # Zwracamy listę braków
        })

    except Exception as e:
        return jsonify({"error": str(e)}), 500


@app.route('/admin/absence', methods=['GET', 'POST'])
def admin_absence_page():
    # 1. ZAPISYWANIE DANYCH (gdy klikniesz "Zapisz")
    if request.method == 'POST':
        person_type = request.form.get('person_type')
        person_id = request.form.get('person_id')
        reason = request.form.get('reason')
        start_date = request.form.get('start_date')
        end_date = request.form.get('end_date')

        if not (person_type and person_id and start_date and end_date):
            return "Brak wymaganych danych!", 400

        try:
            with engine.begin() as conn:
                conn.execute(text("""
                    INSERT INTO absences (person_type, person_id, reason, start_date, end_date)
                    VALUES (:pt, :pid, :reason, :s, :e)
                """), {
                    "pt": person_type,
                    "pid": int(person_id),
                    "reason": reason,
                    "s": start_date,
                    "e": end_date
                })

            # Po zapisie wróć do odpowiedniej listy
            if person_type == 'therapist':
                return redirect(url_for('terapeuta_panel'))  # lub nazwa Twojej funkcji listy terapeutów
            elif person_type == 'driver':
                return redirect(url_for('driver_schedule_page'))  # lub nazwa funkcji listy kierowców
            else:
                return redirect(url_for('main_index'))

        except Exception as e:
            print(f"Błąd zapisu absencji: {e}")
            return f"Błąd bazy danych: {e}", 500

    # 2. WYŚWIETLANIE FORMULARZA (GET)
    person_type = request.args.get('person_type')  # np. 'therapist'
    person_id = request.args.get('person_id')  # np. 24

    if not person_type or not person_id:
        return "Brak parametrów w URL", 400

    # Pobierz imię i nazwisko, żeby wyświetlić w nagłówku
    full_name = "Nieznana osoba"
    try:
        with engine.connect() as conn:
            if person_type == 'therapist':
                full_name = conn.execute(text("SELECT full_name FROM therapists WHERE id=:id"),
                                         {"id": person_id}).scalar()
            elif person_type == 'driver':
                full_name = conn.execute(text("SELECT full_name FROM drivers WHERE id=:id"), {"id": person_id}).scalar()
    except Exception as e:
        print(e)

    return render_template('admin_absence.html',
                           person_type=person_type,
                           person_id=person_id,
                           full_name=full_name)


@app.route('/api/absences', methods=['POST'])
@login_required
def api_add_absence():
    has_access = (
            current_user.is_admin or
            current_user.is_secretariat or
            current_user.has_permission('manage_absences')
    )
    if not has_access:
        return jsonify({"error": "Brak uprawnień."}), 403
        
    data = request.get_json(silent=True) or {}
    person_type = data.get('person_type')
    person_id = data.get('person_id')
    reason = data.get('reason')
    start_date = data.get('start_date')
    end_date = data.get('end_date')

    if not (person_type and person_id and reason and start_date and end_date):
        return jsonify({"error": "Brak wymaganych danych"}), 400

    current_firma_id = session.get('firma_id', 1)

    try:
        with engine.begin() as conn:
            # 1. SPRAWDZENIE KOLIZJI (w obrębie tej samej firmy)
            check_sql = text("""
                SELECT reason, start_date, end_date 
                FROM absences 
                WHERE person_type = :pt 
                  AND person_id = :pid
                  AND start_date <= :new_end 
                  AND end_date >= :new_start
                  AND status != 'cancelled'
                  AND firma_id = :firma_id
            """)
            existing = conn.execute(check_sql, {
                "pt": person_type, "pid": int(person_id),
                "new_start": start_date, "new_end": end_date, "firma_id": current_firma_id
            }).mappings().first()

            if existing:
                return jsonify({"error": "Konflikt terminów nieobecności."}), 409

            # 2. ZAPIS Z POWIĄZANIEM FIRMA_ID
            conn.execute(text("""
                INSERT INTO absences (person_type, person_id, reason, start_date, end_date, status, firma_id)
                VALUES (:pt, :pid, :reason, :s, :e, 'approved', :firma_id)
            """), {
                "pt": person_type, "pid": int(person_id), "reason": reason,
                "s": start_date, "e": end_date, "firma_id": current_firma_id
            })
            
        return jsonify({"success": True, "message": "Nieobecność dodana pomyślnie"}), 201
    except Exception as e:
        return jsonify({"error": str(e)}), 500


@app.route('/api/absences/<int:absence_id>', methods=['DELETE'])
@login_required
def delete_absence(absence_id):
    current_firma_id = session.get('firma_id', 1)
    data = request.get_json(silent=True) or {}
    note = data.get('note', '').strip()

    try:
        with engine.begin() as conn:
            # Sprawdzenie, czy wpis należy do firmy żądającego użytkownika
            existing_row = conn.execute(
                text("SELECT person_type, person_id, reason FROM absences WHERE id = :id AND firma_id = :firma_id"),
                {"id": absence_id, "firma_id": current_firma_id}
            ).mappings().first()

            if not existing_row:
                return jsonify({"error": "Wpis nie istnieje lub brak uprawnień."}), 404

            conn.execute(
                text("UPDATE absences SET status = 'cancelled', cancellation_note = :note WHERE id = :id AND firma_id = :firma_id"),
                {"id": absence_id, "note": note, "firma_id": current_firma_id}
            )
        return jsonify({"message": "Nieobecność została anulowana."}), 200
    except Exception as e:
        return jsonify({"error": str(e)}), 500


@app.route('/admin/history/absences', methods=['GET'])
@admin_required  # Tylko dla admina
def admin_absence_history():
    """Strona z historią nieobecności wszystkich pracowników (Multi-tenant)."""
    current_year = datetime.now().year
    selected_year = request.args.get('year', current_year, type=int)
    
    # Pobranie id firmy z aktualnej sesji zalogowanego admina
    current_firma_id = session.get('firma_id', 1)

    try:
        with engine.connect() as conn:
            # SQL: DODANO KRYTYCZNĄ BLOKADĘ AND a.firma_id = :firma_id
            sql = text("""
                SELECT 
                    a.id, 
                    a.person_type, 
                    a.person_id, 
                    a.reason, 
                    a.start_date, 
                    a.end_date, 
                    a.status,
                    a.cancellation_note,
                    CASE 
                        WHEN a.person_type = 'therapist' THEN t.full_name
                        WHEN a.person_type = 'driver' THEN d.full_name
                        ELSE 'Nieznany' 
                    END as full_name,
                    (a.end_date - a.start_date) + 1 as duration_days
                FROM absences a
                LEFT JOIN therapists t ON a.person_id = t.id AND a.person_type = 'therapist'
                LEFT JOIN drivers d ON a.person_id = d.id AND a.person_type = 'driver'
                WHERE EXTRACT(YEAR FROM a.start_date) = :year
                  AND a.firma_id = :firma_id  -- <--- BLOKADA MULTI-TENANT
                ORDER BY a.start_date DESC
            """)

            rows = conn.execute(sql, {"year": selected_year, "firma_id": current_firma_id}).mappings().all()

            history = []
            for r in rows:
                item = dict(r)
                if item['start_date']: item['start_date'] = item['start_date'].strftime('%Y-%m-%d')
                if item['end_date']: item['end_date'] = item['end_date'].strftime('%Y-%m-%d')
                history.append(item)

            return render_template(
                'absence_history.html',
                history=history,
                selected_year=selected_year,
                current_year=current_year
            )
    except Exception as e:
        print(f"Błąd historii nieobecności: {e}")
        return f"Błąd serwera: {e}", 500


@app.route('/api/keep-alive', methods=['POST'])
def keep_alive():
    """Odświeża sesję użytkownika po stronie serwera."""
    session.modified = True
    return jsonify({'status': 'ok'}), 200


@app.route('/api/admin/users/<int:user_id>', methods=['GET'])
@login_required
def get_user_details(user_id):
    """
    Bezpieczne pobieranie szczegółowych danych użytkownika.
    Odporne na brakujące pola, ciągi tekstowe w datach oraz błędy sesji.
    """
    try:
        with session_scope() as db_session:
            user = db_session.get(User, user_id)
            if not user:
                return jsonify({'error': f'Użytkownik o ID {user_id} nie istnieje.'}), 404

            # Bezpieczne parsowanie daty urodzenia (niezależnie od typu: date, datetime, str czy None)
            birth_date_str = None
            if user.birth_date:
                if hasattr(user.birth_date, 'isoformat'):
                    birth_date_str = user.birth_date.isoformat()
                else:
                    birth_date_str = str(user.birth_date)

            return jsonify({
                "id": user.id,
                "username": user.username or "",
                "full_name": user.full_name or "",
                "email": getattr(user, 'email', '') or "",
                "phone": user.phone or "",
                "birth_date": birth_date_str,
                "is_admin": bool(user.is_admin),
                "is_secretariat": bool(user.is_secretariat),
                "therapist_id": user.therapist_id,
                "driver_id": user.driver_id,
                "permissions": user.permissions or ""
            }), 200

    except Exception as e:
        print(f"❌ Krytyczny błąd w get_user_details (user_id={user_id}): {e}")
        import traceback
        traceback.print_exc()
        return jsonify({'error': f'Wewnętrzny błąd serwera przy pobieraniu użytkownika: {str(e)}'}), 500

@app.route('/api/v1/auto-plan-batch', methods=['POST'])
@login_required
def auto_plan_batch():
    """
    Zaawansowany, masowy planer AI z uwzględnieniem preferencji historycznych.
    W pierwszej kolejności dopasowuje najczęstszego terapeutę, kierowcę oraz ulubiony dzień tygodnia klienta.
    Obsługuje stykające się terminy (np. koniec 10:00, start kolejnego o 10:00) bez kolizji.
    """
    import math
    import random
    from sqlalchemy import text
    
    data = request.json or {}
    start_date_str = data.get('start_date')
    end_date_str = data.get('end_date')
    excluded_ids = data.get('excluded_ids', [])
    current_firma_id = session.get('firma_id', 1)

    if not start_date_str or not end_date_str: 
        return jsonify({'error': 'Brak zakresu dat'}), 400

    start_date = datetime.strptime(start_date_str, '%Y-%m-%d').date()
    end_date = datetime.strptime(end_date_str, '%Y-%m-%d').date()

    # Wyznaczamy dni robocze do zaplanowania
    planning_days = []
    curr = start_date
    while curr <= end_date:
        if curr.weekday() < 5: 
            planning_days.append(curr)
        curr += timedelta(days=1)

    if not planning_days:
        return jsonify({"error": "Wybrany zakres nie zawiera dni roboczych."}), 400

    try:
        with session_scope() as session_db:
            # Filtrujemy zasoby po firmie w modelu SaaS
            all_clients = session_db.query(Client).filter_by(active=True, firma_id=current_firma_id).all()
            raw_clients = [c for c in all_clients if c.id not in excluded_ids]
            drivers = session_db.query(Driver).filter_by(active=True, firma_id=current_firma_id).all()
            therapists = session_db.query(Therapist).filter_by(active=True, firma_id=current_firma_id).all()
            unav_records = session_db.query(ClientUnavailability).filter_by(firma_id=current_firma_id).all()

            if not raw_clients:
                return jsonify({"error": "Brak klientów do zaplanowania."}), 400

            # --- STREAMING_CHUNK: Analiza historii preferencji (Terapeuci, Kierowcy, Dni Tygodnia) ---
            
            # 1. Jak często z danym terapeutą ma klient (Therapist Frequency Map)
            th_history_sql = text("""
                SELECT client_id, therapist_id, COUNT(*) as cnt
                FROM schedule_slots
                WHERE kind = 'therapy' AND status != 'cancelled' AND firma_id = :fid
                GROUP BY client_id, therapist_id
                ORDER BY client_id, cnt DESC
            """)
            th_history_rows = session_db.execute(th_history_sql, {"fid": current_firma_id}).mappings().all()
            
            client_therapist_prefs = {}
            for r in th_history_rows:
                cid, tid, cnt = r['client_id'], r['therapist_id'], r['cnt']
                if tid is None:
                    continue
                if cid not in client_therapist_prefs:
                    client_therapist_prefs[cid] = []
                client_therapist_prefs[cid].append(tid)

            # 2. Jak często z danym kierowcą jeździ klient (Driver Frequency Map)
            dr_history_sql = text("""
                SELECT client_id, driver_id, COUNT(*) as cnt
                FROM schedule_slots
                WHERE kind IN ('pickup', 'dropoff') AND status != 'cancelled' AND firma_id = :fid
                GROUP BY client_id, driver_id
                ORDER BY client_id, cnt DESC
            """)
            dr_history_rows = session_db.execute(dr_history_sql, {"fid": current_firma_id}).mappings().all()
            
            client_driver_prefs = {}
            for r in dr_history_rows:
                cid, did, cnt = r['client_id'], r['driver_id'], r['cnt']
                if did is None:
                    continue
                if cid not in client_driver_prefs:
                    client_driver_prefs[cid] = []
                client_driver_prefs[cid].append(did)

            # 3. W jakie dni tygodnia ma klient zajęcia (ISO DOW: 1=Pon, 7=Niedz)
            dow_history_sql = text("""
                SELECT client_id, EXTRACT(ISODOW FROM starts_at) as dow, COUNT(*) as cnt
                FROM schedule_slots
                WHERE kind = 'therapy' AND status != 'cancelled' AND firma_id = :fid
                GROUP BY client_id, dow
                ORDER BY client_id, cnt DESC
            """)
            dow_history_rows = session_db.execute(dow_history_sql, {"fid": current_firma_id}).mappings().all()
            
            client_dow_prefs = {}
            for r in dow_history_rows:
                cid, dow, cnt = r['client_id'], int(r['dow']), r['cnt']
                if cid not in client_dow_prefs:
                    client_dow_prefs[cid] = {}
                client_dow_prefs[cid][dow] = cnt

            # --- STREAMING_CHUNK: Wczytywanie istniejących rezerwacji bazy danych ---
            # Pobieramy zapisane już zajęte sloty w zadanym okresie, by uniknąć nadpisania
            busy_slots_sql = text("""
                SELECT id, therapist_id, driver_id, client_id, starts_at, ends_at, kind
                FROM schedule_slots
                WHERE status != 'cancelled' AND firma_id = :fid
                  AND starts_at >= :start AND ends_at <= :end
            """)
            existing_busy_rows = session_db.execute(busy_slots_sql, {
                "fid": current_firma_id, 
                "start": datetime.combine(start_date, datetime.min.time()), 
                "end": datetime.combine(end_date, datetime.max.time())
            }).mappings().all()

            # Dynamiczne tablice zajętości w pamięci RAM na czas planowania masowego
            busy_therapists = {t.id: [] for t in therapists}
            busy_drivers = {d.id: [] for d in drivers}
            busy_clients = {c.id: [] for c in raw_clients}

            for r in existing_busy_rows:
                starts, ends = r['starts_at'], r['ends_at']
                if r['therapist_id'] and r['therapist_id'] in busy_therapists:
                    busy_therapists[r['therapist_id']].append((starts, ends))
                if r['driver_id'] and r['driver_id'] in busy_drivers:
                    busy_drivers[r['driver_id']].append((starts, ends))
                if r['client_id'] and r['client_id'] in busy_clients:
                    busy_clients[r['client_id']].append((starts, ends))

            # --- STREAMING_CHUNK: Separacja klientów pod kątem logistyki tras... ---
            clients_with_location = []
            clients_without_location = []

            for c in raw_clients:
                if c.latitude and c.longitude:
                    clients_with_location.append(c)
                else:
                    clients_without_location.append(c)

            # Mapa niedostępności klienta ze szkoły/innych placówek
            unav_map = {}
            for r in unav_records:
                if r.client_id not in unav_map: 
                    unav_map[r.client_id] = []
                unav_map[r.client_id].append(r)

            # --- STREAMING_CHUNK: Klastrowanie geograficzne tras i pozycjonowanie... ---
            unassigned_clients = list(clients_with_location)
            client_clusters = []

            # Grupowanie geograficzne (max 3 osoby w promieniu 5 km)
            while unassigned_clients:
                seed_client = unassigned_clients.pop(0)
                cluster = [seed_client]

                for i in range(len(unassigned_clients) - 1, -1, -1):
                    candidate = unassigned_clients[i]
                    dist = calculate_distance(
                        seed_client.latitude, seed_client.longitude,
                        candidate.latitude, candidate.longitude
                    )
                    if dist <= 5.0 and len(cluster) < 3:
                        cluster.append(candidate)
                        unassigned_clients.pop(i)

                client_clusters.append(cluster)

            # Dołączamy pacjentów bez adresu jako osobne jednorazowe pakiety
            for c_no_addr in clients_without_location:
                client_clusters.append([c_no_addr])

            # --- STREAMING_CHUNK: Konstrukcja bezkolizyjnych matryc czasowych... ---
            planned_slots = []
            warnings = []

            # Pomocnicza funkcja sprawdzająca czy terminy się zazębiają (Touching Slots Support)
            # Używa operatorów bez "=" (start1 < koniec_zajety AND koniec1 > start_zajety), co pozwala na styk 10:00 - 10:00!
            def is_overlapping_local(start1, end1, busy_list):
                for b_start, b_end in busy_list:
                    # Zamiana na datetime bez strefy dla bezpieczeństwa porównań
                    bs_naive = b_start.replace(tzinfo=None) if b_start.tzinfo else b_start
                    be_naive = b_end.replace(tzinfo=None) if b_end.tzinfo else b_end
                    s1_naive = start1.replace(tzinfo=None) if start1.tzinfo else start1
                    e1_naive = end1.replace(tzinfo=None) if end1.tzinfo else end1
                    
                    if s1_naive < be_naive and e1_naive > bs_naive:
                        return True
                return False

            def is_client_unavailability_blocked(c_id, visit_dt):
                day_name_eng = visit_dt.strftime('%A')
                days_mapping = {
                    "Monday": ["Monday", "Poniedziałek"],
                    "Tuesday": ["Tuesday", "Wtorek"],
                    "Wednesday": ["Wednesday", "Środa"],
                    "Thursday": ["Thursday", "Czwartek"],
                    "Friday": ["Friday", "Piątek"]
                }
                rules = unav_map.get(c_id, [])
                check_start = visit_dt.time()
                check_end = (visit_dt + timedelta(minutes=45)).time()

                for rule in rules:
                    possible_days = days_mapping.get(day_name_eng, [])
                    if rule.day_of_week in possible_days:
                        if check_start < rule.end_time and check_end > rule.start_time:
                            return True
                return False

            start_hours = [8, 10, 13, 15]

            # Pętla generowania kalendarza
            for target_date in planning_days:
                date_str = target_date.strftime('%Y-%m-%d')
                iso_dow = target_date.isoweekday() # 1 = Poniedziałek, 5 = Piątek

                # Sortujemy klastry pod kątem preferencji dnia tygodnia dla bieżącego dnia roboczego!
                # Klastry zawierające pacjentów, którzy najczęściej mają zajęcia w ten dzień tygodnia, lecą na przód kolejki!
                def get_cluster_dow_score(cls):
                    score = 0
                    for client in cls:
                        score += client_dow_prefs.get(client.id, {}).get(iso_dow, 0)
                    return score

                client_clusters.sort(key=get_cluster_dow_score, reverse=True)

                for cluster in client_clusters:
                    is_transport_possible = bool(cluster[0].latitude)
                    
                    # Szukamy wolnej konfiguracji godzinowej dla klastra
                    allocated_time = None
                    allocated_therapist_by_client = {}
                    allocated_driver = None

                    # Sprawdzamy standardowe ramówki godzinowe poradni
                    for base_hour in start_hours:
                        base_dt = datetime.combine(target_date, datetime.min.time()) + timedelta(hours=base_hour)
                        
                        # Walidacja czy wszyscy klienci w klastrze są wolni w tym oknie czasowym
                        cluster_free = True
                        for idx, client in enumerate(cluster):
                            v_start = base_dt + timedelta(minutes=45 * idx)
                            v_end = v_start + timedelta(minutes=45)
                            if is_overlapping_local(v_start, v_end, busy_clients.get(client.id, [])) or is_client_unavailability_blocked(client.id, v_start):
                                cluster_free = False
                                break
                        
                        if not cluster_free:
                            continue

                        # Dobór Terapeutów na podstawie historii i częstotliwości pracy (Therapist Affinity Heuristics)
                        temp_therapists = {}
                        therapists_match_ok = True
                        
                        for idx, client in enumerate(cluster):
                            v_start = base_dt + timedelta(minutes=45 * idx)
                            v_end = v_start + timedelta(minutes=45)
                            
                            # Pobieramy posortowaną listę ulubionych terapeutów tego klienta
                            preferred_tids = client_therapist_prefs.get(client.id, [])
                            
                            # Budujemy listę wszystkich aktywnych terapeutów (ulubieni pierwsi, potem reszta)
                            fallback_tids = [t.id for t in therapists if t.id not in preferred_tids]
                            search_tids = preferred_tids + fallback_tids
                            
                            matched_tid = None
                            for tid in search_tids:
                                if not is_overlapping_local(v_start, v_end, busy_therapists.get(tid, [])):
                                    matched_tid = tid
                                    break
                            
                            if matched_tid:
                                temp_therapists[client.id] = matched_tid
                            else:
                                therapists_match_ok = False # Brak wolnego terapeuty na ten slot
                                break
                        
                        if not therapists_match_ok:
                            continue

                        # Dobór Kierowcy na podstawie historii przewozów (Driver Affinity Heuristics)
                        temp_driver_id = None
                        if is_transport_possible and drivers:
                            # Trasa transportu klastra: od pierwszego odbioru do końca odwozu
                            p_start = base_dt - timedelta(minutes=30)
                            p_end = base_dt + timedelta(minutes=45 * len(cluster)) + timedelta(minutes=30)
                            
                            # Najczęstszy kierowca dla lidera klastra
                            preferred_dids = client_driver_prefs.get(cluster[0].id, [])
                            fallback_dids = [d.id for d in drivers if d.id not in preferred_dids]
                            search_dids = preferred_dids + fallback_dids

                            for did in search_dids:
                                if not is_overlapping_local(p_start, p_end, busy_drivers.get(did, [])):
                                    temp_driver_id = did
                                    break
                            
                            if not temp_driver_id:
                                continue # Brak wolnego kierowcy na ten przedział trasy

                        # Znaleźliśmy optymalną konfigurację!
                        allocated_time = base_dt
                        allocated_therapist_by_client = temp_therapists
                        allocated_driver = temp_driver_id
                        break

                    # Zapisujemy wygenerowane sloty i aktualizujemy dynamiczną zajętość w RAM
                    if allocated_time:
                        for idx, client in enumerate(cluster):
                            v_start = allocated_time + timedelta(minutes=45 * idx)
                            v_end = v_start + timedelta(minutes=45)
                            tid = allocated_therapist_by_client[client.id]

                            # Blokujemy zasoby lokalnie
                            busy_clients[client.id].append((v_start, v_end))
                            busy_therapists[tid].append((v_start, v_end))
                            
                            explanation_parts = []
                            if not is_transport_possible:
                                explanation_parts.append("⛔ BRAK ADRESU (Bez transportu)")
                            elif len(cluster) > 1:
                                explanation_parts.append(f"Grupa ({idx + 1}/{len(cluster)})")
                            else:
                                explanation_parts.append("Indywidualny")

                            # Informacja o dopasowaniu w celach diagnostycznych
                            is_favorite_therapist = tid in client_therapist_prefs.get(client.id, [])[:1]
                            explanation_parts.append("⭐ Preferowany terapeuta" if is_favorite_therapist else "Dobór automatyczny")

                            if allocated_driver:
                                p_start = allocated_time - timedelta(minutes=30)
                                p_end = allocated_time + timedelta(minutes=45 * len(cluster)) + timedelta(minutes=30)
                                busy_drivers[allocated_driver].append((p_start, p_end))
                                
                                is_favorite_driver = allocated_driver in client_driver_prefs.get(client.id, [])[:1]
                                if is_favorite_driver:
                                    explanation_parts.append("🚌 Preferowany kierowca")

                            planned_slots.append({
                                "client_id": client.id,
                                "client_name": client.full_name,
                                "therapist_id": tid,
                                "driver_id": allocated_driver,
                                "driver_name": session_db.get(Driver, allocated_driver).full_name if allocated_driver else None,
                                "starts_at": v_start.strftime('%Y-%m-%d %H:%M'),
                                "ends_at": v_end.strftime('%Y-%m-%d %H:%M'),
                                "explanation": " - ".join(explanation_parts)
                            })
                    else:
                        warnings.append(f"Nie udało się znaleźć wolnego terminu dla klastra pacjenta {cluster[0].full_name} w dniu {date_str}.")

        # Zwrot wyników do frontendu
        warnings.append(f"Sukces: Zaplanowano {len(planned_slots)} bezkolizyjnych wizyt.")
        return jsonify({
            "planned": planned_slots,
            "warnings": warnings
        }), 200

    except Exception as e:
        print(f"❌ Krytyczny błąd planowania masowego AI: {e}")
        import traceback
        traceback.print_exc()
        return jsonify({"error": f"Wewnętrzny błąd planera: {str(e)}"}), 500

        
@admin_bp.route('/api/admin/users', methods=['POST'])
@admin_required
def create_new_user_api():
    """
    Tworzy nowego użytkownika z opcją automatycznego generowania
    profilu Terapeuty lub Kierowcy.
    """
    data = request.get_json()

    # 1. Walidacja podstawowa
    if not data or 'username' not in data or 'password' not in data or 'full_name' not in data:
        return jsonify({'error': 'Wymagane pola: Login, Hasło, Imię i Nazwisko'}), 400

    username = data['username'].strip()
    full_name = data['full_name'].strip()
    password = data['password']

    if len(password) < 4:
        return jsonify({'error': 'Hasło musi mieć co najmniej 4 znaki.'}), 400

    try:
        with session_scope() as db_session:
            # 2. Sprawdź unikalność loginu
            if db_session.query(User).filter_by(username=username).first():
                return jsonify({'error': f"Login '{username}' jest już zajęty."}), 409

            # 3. Logika Automatyzacji (Tworzenie profili)

            # --- TERAPEUTA ---
            therapist_id = data.get('therapist_id')
            if not therapist_id and data.get('auto_create_therapist'):
                existing_th = db_session.query(Therapist).filter(
                    func.lower(Therapist.full_name) == func.lower(full_name)
                ).first()
                if existing_th:
                    therapist_id = existing_th.id
                else:
                    new_th = Therapist(full_name=full_name, active=True)
                    db_session.add(new_th)
                    db_session.flush()
                    therapist_id = new_th.id

            # --- KIEROWCA ---
            driver_id = data.get('driver_id')
            if not driver_id and data.get('auto_create_driver'):
                existing_dr = db_session.query(Driver).filter(
                    func.lower(Driver.full_name) == func.lower(full_name)
                ).first()
                if existing_dr:
                    driver_id = existing_dr.id
                else:
                    new_dr = Driver(full_name=full_name, active=True)
                    db_session.add(new_dr)
                    db_session.flush()
                    driver_id = new_dr.id

            # 4. Parsowanie daty urodzenia
            birth_date_obj = None
            if data.get('birth_date'):
                try:
                    birth_date_obj = datetime.fromisoformat(data['birth_date']).date()
                except ValueError:
                    pass

            # 5. Uprawnienia
            perms_str = ""
            if 'permissions' in data and isinstance(data['permissions'], list):
                perms_str = ",".join(data['permissions'])

            # 6. Tworzenie Użytkownika (BEZ POLA EMAIL, KTÓRE POWODOWAŁO BŁĄD)
            new_user = User(
                username=username,
                full_name=full_name,
                # email=data.get('email'),  <-- USUNIĘTO TĘ LINIĘ
                phone=data.get('phone'),
                birth_date=birth_date_obj,
                is_admin=data.get('is_admin', False),
                is_secretariat=data.get('is_secretariat', False),
                permissions=perms_str,
                therapist_id=therapist_id,
                driver_id=driver_id
            )

            new_user.set_password(password)
            db_session.add(new_user)
            db_session.flush()

            return jsonify({
                'message': 'Użytkownik utworzony pomyślnie.',
                'user_id': new_user.id,
                'created_therapist': bool(therapist_id and data.get('auto_create_therapist')),
                'created_driver': bool(driver_id and data.get('auto_create_driver'))
            }), 201

    except Exception as e:
        print(f"❌ Błąd tworzenia użytkownika: {e}")
        import traceback
        traceback.print_exc()
        return jsonify({'error': f"Błąd serwera: {str(e)}"}), 500


@admin_bp.route('/api/admin/users/<int:user_id>', methods=['PUT'])
@admin_required
def update_user(user_id):
    """Aktualizuje dane użytkownika ORAZ powiązania profili."""
    data = request.get_json()
    admin_id = session.get('user_id')

    if not data or 'full_name' not in data:
        return jsonify({'error': 'Brak danych do aktualizacji'}), 400

    try:
        with session_scope() as db_session:
            user = db_session.get(User, user_id)
            if not user:
                return jsonify({'error': 'Użytkownik nie znaleziony'}), 404

            # 1. Aktualizacja pól podstawowych
            user.full_name = data['full_name'].strip()
            user.username = data['username'].strip()
            user.phone = data.get('phone', user.phone)

            # Data urodzenia
            birth_date_str = data.get('birth_date')
            if birth_date_str:
                try:
                    user.birth_date = datetime.fromisoformat(birth_date_str).date()
                except ValueError:
                    user.birth_date = None
            elif 'birth_date' in data and data['birth_date'] is None:
                user.birth_date = None

            # 2. Aktualizacja hasła
            if 'password' in data and data['password']:
                if len(data['password']) < 4:
                    return jsonify({'error': 'Hasło za krótkie.'}), 400
                user.set_password(data['password'])

            # 3. Aktualizacja ról (Admin/Sekretariat)
            # Zabezpieczenie: nie odbieraj admina samemu sobie
            if user_id != admin_id:
                if 'is_admin' in data: user.is_admin = data['is_admin']

            if 'is_secretariat' in data: user.is_secretariat = data['is_secretariat']

            # 4. Aktualizacja uprawnień (Permissions)
            if 'permissions' in data:
                perms_list = data['permissions']
                user.permissions = ",".join(perms_list) if isinstance(perms_list, list) else ""

            # =========================================================
            # === BRAKUJĄCY FRAGMENT: POWIĄZANIA PROFILI (LINKING) ===
            # =========================================================

            # 5. Profil Terapeuty
            if 'therapist_id' in data:
                tid = data['therapist_id']
                # Konwersja: pusty string lub "0" zamień na None
                user.therapist_id = int(tid) if tid and str(tid) != "" else None

            # 6. Profil Kierowcy
            if 'driver_id' in data:
                did = data['driver_id']
                # Konwersja: pusty string lub "0" zamień na None
                user.driver_id = int(did) if did and str(did) != "" else None
            # =========================================================

            # Commit nastąpi automatycznie dzięki session_scope

            print(f"Zaktualizowano User ID {user.id}. T_ID={user.therapist_id}, D_ID={user.driver_id}")

            return jsonify({
                'message': 'Zaktualizowano pomyślnie.',
                'id': user.id
            }), 200

    except IntegrityError:
        return jsonify({'error': 'Login jest już zajęty.'}), 409
    except Exception as e:
        print(f"Błąd update_user: {e}")
        return jsonify({'error': str(e)}), 500


@admin_bp.route('/api/admin/users/<int:user_id>/link', methods=['POST'])
@admin_required
def link_user_profiles(user_id):
    """API Endpoint do aktualizacji powiązań profilu terapeuty/kierowcy."""
    data = request.get_json()
    if data is None:
        return jsonify({'error': 'Brak danych JSON'}), 400

    # Używamy .get() aby pozwolić na wysłanie 'null' lub brak klucza
    therapist_id = data.get('therapist_id')
    driver_id = data.get('driver_id')

    # Konwertuj puste wartości (np. 0 lub pusty string "") na None (NULL w bazie)
    if not therapist_id: therapist_id = None
    if not driver_id: driver_id = None

    try:
        with session_scope() as db_session:
            user = db_session.get(User, user_id)
            if not user:
                return jsonify({'error': 'Użytkownik nie znaleziony'}), 404

            # Zaktualizuj ID profili
            user.therapist_id = therapist_id
            user.driver_id = driver_id

            # session_scope() automatycznie wykona commit

            print(
                f"Admin (ID: {session.get('user_id')}) zaktualizował powiązania dla User ID: {user_id}. Nowe T_ID={therapist_id}, D_ID={driver_id}")
            return jsonify({'message': 'Powiązania zaktualizowane pomyślnie'}), 200

    except Exception as e:
        # session_scope() automatycznie wykona rollback
        print(f"Błąd podczas aktualizacji powiązań użytkownika: {e}")
        traceback.print_exc()
        return jsonify({'error': f'Błąd serwera: {str(e)}'}), 500


@app.route('/admin/logs')
@admin_required
def admin_logs_page():
    """Wyświetla logi systemowe TYLKO dla bieżącej firmy (Multi-tenant)"""
    current_firma_id = session.get('firma_id', 1)
    
    with session_scope() as db_session:
        # DODAJ FILTR .filter(SystemLog.firma_id == current_firma_id)
        logs = db_session.query(SystemLog).filter(
            SystemLog.firma_id == current_firma_id  # <--- TEN FILTR!
        ).order_by(SystemLog.created_at.desc()).limit(500).all()
        
        return render_template('admin_logs.html', logs=logs)


# =========================================================================
# === DODANE BRAKUJĄCE ENDPOINTY DLA SELECT2 W FORMULARZU GRUP TUS (FRONTEND) ===
# =========================================================================

@app.route('/api/users', methods=['GET'])
@login_required
def list_users():
    """Zwraca listę kont użytkowników wyłącznie dla aktualnie zalogowanej firmy."""
    if not (current_user.is_admin or current_user.has_permission('manage_users')):
        return jsonify({"error": "Brak uprawnień do przeglądania listy użytkowników."}), 403

    current_firma_id = session.get('firma_id', 1)

    try:
        with SessionLocal() as s:
            users = (
                s.query(User)
                .filter(User.firma_id == current_firma_id)  # <--- TEN FILTR!
                .filter(User.username != 'admin')
                .order_by(User.username)
                .all()
            )
            
            result = []
            for u in users:
                result.append({
                    "id": u.id,
                    "username": u.username,
                    "full_name": u.full_name,
                    "is_admin": u.is_admin,
                    "is_secretariat": u.is_secretariat,
                    "therapist_id": u.therapist_id,
                    "permissions": u.permissions if u.permissions else ""
                })
                
            return jsonify(result), 200
    except Exception as e:
        print(f"❌ Błąd podczas pobierania kont użytkowników: {e}")
        return jsonify({'error': str(e)}), 500



# =========================================================================


@admin_bp.route('/api/admin/users', methods=['GET'])
@admin_required
def get_all_users_for_reset():
    """Zwraca listę użytkowników TYLKO z bieżącej firmy (Multi-tenant)"""
    current_admin_id = session.get('user_id')
    current_firma_id = session.get('firma_id', 1)  # <--- KLUCZOWE!
    
    try:
        with session_scope() as db_session:
            # DODAJ FILTR .filter(User.firma_id == current_firma_id)
            users = db_session.query(User).filter(
                User.id != current_admin_id,
                User.firma_id == current_firma_id  # <--- TEN FILTR NAPRAWIA PROBLEM!
            ).order_by(User.full_name).all()

            users_list = [{
                'id': user.id,
                'username': user.username,
                'full_name': user.full_name
            } for user in users]

            return jsonify(users_list), 200

    except Exception as e:
        print(f"Błąd pobierania listy użytkowników: {e}")
        return jsonify({'error': 'Wystąpił błąd serwera podczas pobierania użytkowników.'}), 500


# -------------------------------------------------------------------

def secretariat_required(view):
    """
    Dostęp dla: Admina, Sekretariatu LUB osoby z uprawnieniem 'poczekalnia'.
    """

    @functools.wraps(view)
    @login_required
    def wrapped_view(**kwargs):

        # 1. Pobierz statusy z sesji
        is_admin = session.get('is_admin')
        is_secretariat = session.get('is_secretariat') is True

        # 2. Sprawdź dedykowane uprawnienie (np. 'poczekalnia')
        # Używamy current_user, który jest dostępny dzięki @login_required
        has_perm = (
            current_user.has_permission('poczekalnia') or
            current_user.has_permission('dziennik') or
            current_user.has_permission('client_panel') or
            current_user.has_permission('resolutions') or
            current_user.has_permission('drivers')
        )

        # 3. Logika OR: Wystarczy jeden z warunków
        if is_admin or is_secretariat or has_perm:
            return view(**kwargs)

        # Brak uprawnień
        flash('Nie masz uprawnień (sekretariatu), aby uzyskać dostęp do tej strony.', 'warning')

        if request.path.startswith('/api/'):
            return jsonify(message="Secretariat privileges required"), 403

        return redirect(url_for('main_index'))

    return wrapped_view


# Upewnij się, że masz import na górze pliku:
import logging


def driver_required(view):
    @functools.wraps(view)
    @login_required
    def wrapped_view(**kwargs):
        # 1. Odświeżamy usera z bazy
        with session_scope() as db_session:
            # Używamy db_session.get, aby uniknąć błędu LegacyAPIWarning
            user = db_session.get(User, current_user.id)

            # Pobieramy dane
            u_perms = user.permissions or ""
            is_admin = user.is_admin
            is_driver = user.driver_id is not None
            is_secretariat = user.is_secretariat

            # Sprawdzanie uprawnienia 'drivers' (z usuwaniem spacji)
            perms_list = [p.strip() for p in u_perms.split(',')]
            has_perm = 'drivers' in perms_list

            # --- DIAGNOSTYKA WIDOCZNA W KONSOLI ---
            logging.warning("=" * 40)
            logging.warning(f"DEBUG DOSTĘPU DLA: {user.username}")
            logging.warning(f"Admin: {is_admin} | Kierowca: {is_driver} | Sekretariat: {is_secretariat}")
            logging.warning(f"Surowe uprawnienia w bazie: '{u_perms}'")
            logging.warning(f"Lista po podziale: {perms_list}")
            logging.warning(f"Czy ma 'drivers'? -> {has_perm}")
            logging.warning("=" * 40)
            # --------------------------------------

            if is_admin or is_driver or is_secretariat or has_perm:
                return view(**kwargs)

        # Jeśli odmowa:
        flash('Brak uprawnień (Logistyka).', 'danger')
        return redirect(url_for('main_index'))

    return wrapped_view


# tu trzeba dodać, aby działały uprawnienia
@app.context_processor
def inject_session_vars():
    return {
        'session': session,  # Zapewnia kompatybilność wsteczną

        # Wprowadź user_login, aby mieć czysty dostęp w nowych miejscach
        # 'user_login': session.get('login', 'Gość'),

        'is_admin': session.get('is_admin', False),
        'therapist_id': session.get('therapist_id'),
        'is_secretariat': session.get('is_secretariat', False),
        'driver_id': session.get('driver_id')
    }


@app.route('/import-planu')
@login_required
def import_planu_page():
    # Sprawdzenie ról użytkownika (przykład)
    # Możesz to dostosować do swojego modelu User
    with session_scope() as db:
        is_therapist = db.query(Therapist).filter_by(user_id=current_user.id).first() is not None
        is_driver = db.query(Driver).filter_by(user_id=current_user.id).first() is not None

    return render_template('import_planu.html',
                           is_admin=current_user.is_admin,
                           current_user=current_user,
                           is_therapist=is_therapist,
                           is_driver=is_driver)


# tymczasowa naprawa hasła
# @app.route('/api/reset-admin-password-force', methods=['POST'])
# def reset_admin_password_force():
#    """
#    Tymczasowy endpoint do *wymuszonego* zresetowania hasła admina.
#    Użyj go RAZ po wdrożeniu, a potem usuń/zakomentuj.
#    """
#    admin_username = 'admin'
#    new_password = 'admin123' # Możesz zmienić na inne, jeśli chcesz

#    print(f"--- Wymuszone resetowanie hasła dla '{admin_username}' ---")
#    try:
#        with session_scope() as db_session:
#            admin_user = db_session.query(User).filter_by(username=admin_username).first()

#           if admin_user:
#               print(f"Znaleziono użytkownika '{admin_username}'. Stary hash (preview): {admin_user.password_hash[:30]}...")
#               # Używamy metody set_password, która generuje poprawny hash
#               admin_user.set_password(new_password)
#               db_session.flush() # Wymuś zapis przed commitem
#              print(f"Nowy hash (preview): {admin_user.password_hash[:30]}...")
#              # session_scope() automatycznie zrobi commit po wyjściu z bloku 'with'
#              print(f"Hasło dla '{admin_username}' zostało zresetowane na '{new_password}'.")
#              return jsonify({'message': f'Hasło dla {admin_username} zostało zresetowane.'}), 200
#          else:
#             print(f"Użytkownik '{admin_username}' nie istnieje w bazie.")
#              return jsonify({'error': f'Użytkownik {admin_username} nie istnieje'}), 404

#   except Exception as e:
#       print(f"BŁĄD podczas resetowania hasła: {str(e)}")
#       import traceback
#       traceback.print_exc()
# session_scope() automatycznie zrobi rollback w razie błędu
#       return jsonify({'error': f'Błąd serwera podczas resetowania hasła: {str(e)}'}), 500




@auth_bp.route('/login', methods=['GET'])
def login_page():
    # ZMIANA: Używamy Flask-Login zamiast surowej sesji
    # Jeśli Flask-Login uważa, że jesteś zalogowany -> idź do dashboardu
    if current_user.is_authenticated:
        return redirect(url_for('main_index'))

    # Jeśli nie jesteś zalogowany (nawet jak masz śmieci w sesji) -> pokaż formularz
    return render_template('login.html', error=None)


'''def create_default_user():
    #"""Tworzy domyślnego użytkownika admin jeśli tabela users jest pusta lub naprawia istniejącego"""
    try:
        with session_scope() as db_session:
            admin_user = db_session.query(User).filter_by(username='admin').first()

            if not admin_user:
                # Tworzymy domyślnego admina
                admin_user = User(username='admin', is_admin=True)
                admin_user.set_password('admin123')
                db_session.add(admin_user)
                print("=" * 50)
                print("UTWORZONO DOMYŚLNEGO UŻYTKOWNIKA:")
                print("Nazwa użytkownika: admin")
                print("Hasło: admin123")
                print("=" * 50)
            else:
                # Sprawdź czy hasło jest poprawne, jeśli nie - napraw
                try:
                    # Testujemy czy hasło działa
                    test_result = admin_user.check_password('admin123')
                    if not test_result:
                        # Jeśli nie działa, ustaw nowe hasło
                        admin_user.set_password('admin123')
                        db_session.commit()
                        print("=" * 50)
                        print("NAPRAWIONO HASŁO ADMINA:")
                        print("Nowe hasło: admin123")
                        print("=" * 50)
                except Exception as e:
                    # Jeśli jest błąd z hashowaniem, napraw
                    print(f"Błąd hashowania: {e}, naprawiam...")
                    admin_user.set_password('admin123')
                    db_session.commit()
                    print("=" * 50)
                    print("NAPRAWIONO USZKODZONE HASŁO ADMINA")
                    print("Nowe hasło: admin123")
                    print("=" * 50)

    except Exception as e:
        print(f"Błąd tworzenia/naprawy użytkownika: {e}")
        import traceback
        traceback.print_exc()'''


@auth_bp.route('/api/login', methods=['POST'])
def handle_login():
    data = request.get_json()
    print(f"Login attempt for: {data.get('username')}")

    if not data or 'username' not in data or 'password' not in data:
        return jsonify({'error': 'Brak nazwy użytkownika lub hasła'}), 400

    username = data.get('username')
    password = data.get('password')

    with session_scope() as db_session:
        user = db_session.query(User).filter_by(username=username).first()

        if user:
            # WAŻNE: Odłączamy obiekt od sesji bazy, żeby można go było użyć w login_user
            # (Inaczej Flask może rzucić błąd, że obiekt jest "detached" po zamknięciu sesji)
            db_session.expunge(user)

            print(f"User found: {user.username}, password_hash: {user.password_hash[:50]}...")
            try:
                password_correct = user.check_password(password)
                print(f"Password check result: {password_correct}")

                if password_correct:
                    # ========================================================
                    # KLUCZOWA ZMIANA - TO NAPRAWIA PROBLEM PRZEKIEROWAŃ
                    # ========================================================
                    login_user(user)
                    # ========================================================

                    # Te ręczne wpisy w sesji możesz zostawić (jeśli używasz ich w innym miejscu),
                    # ale to login_user() wyżej robi najważniejszą robotę.
                    session.clear()  # Czyścimy stare śmieci, ale login_user() zaraz ustawi swoje

                    # Musimy przywrócić sesję usera po clear()
                    login_user(user)

                    # Twoje dodatkowe dane w sesji
                    session['user_id'] = user.id
                    session['username'] = user.username
                    session['is_admin'] = user.is_admin
                    session['is_secretariat'] = user.is_secretariat
                    session['therapist_id'] = user.therapist_id
                    session['driver_id'] = user.driver_id
                    session['firma_id'] = user.firma_id

                    # log_msg = f"ID: {username} ({data.get('username')})."
                    # log_activity("Logowanie ", log_msg)
                    log_activity("LOGIN_SUCCESS", f"Zalogowano użytkownika: {username} ({data.get('username')}")
                    return jsonify({'redirect_url': url_for('main_index')})

                else:
                    # print(f"Invalid password for: {username}")
                    log_activity("LOGIN_FAILED", f"Nieudana próba logowania dla: {username}", level="WARNING")
                    return jsonify({'error': 'Niepoprawna nazwa użytkownika lub hasło.'}), 401

            except Exception as e:
                print(f"Password check error: {e}")
                return jsonify({'error': f'Błąd systemu uwierzytelniania: {str(e)}'}), 500
        else:
            print(f"User not found: {username}")
            return jsonify({'error': 'Niepoprawna nazwa użytkownika lub hasło.'}), 401


@auth_bp.route('/logout')
@login_required
def logout():
    session.clear()
    flash('Zostałeś pomyślnie wylogowany.')
    return redirect(url_for('auth.login_page'))


# === BLUEPRINT: Rejestracja tylko dla Admina ===


@admin_bp.route('/admin/register', methods=['GET'])
@admin_required
def admin_register_page():
    return render_template('admin_register.html')


# @admin_bp.route('/admin/manage-user', methods=['GET'])
# @admin_required
# def admin_manager_page():
#    return render_template('manage_users.html')

@admin_bp.route('/api/admin/register', methods=['POST'])
@admin_required
def handle_admin_register():
    data = request.get_json()

    # Walidacja danych wejściowych
    if not data or 'username' not in data or 'password' not in data or 'full_name' not in data:
        return jsonify({'error': 'Nazwa użytkownika, hasło i Imię i Nazwisko są wymagane'}), 400

    username = data['username'].strip()
    password = data['password']
    full_name = data['full_name'].strip()

    # Pobieranie i konwersja nowych pól
    phone = data.get('phone')
    birth_date_str = data.get('birth_date')
    birth_date_obj = None
    if birth_date_str:
        try:
            birth_date_obj = datetime.fromisoformat(birth_date_str).date()
        except ValueError:
            return jsonify({'error': 'Nieprawidłowy format daty urodzenia. Oczekiwano YYYY-MM-DD'}), 400

    # Pobieranie flag ról
    is_admin_flag = data.get('is_admin', False)
    is_secretariat_flag = data.get('is_secretariat', False)

    if not username or not password or not full_name:
        return jsonify({'error': 'Wszystkie wymagane pola muszą być wypełnione'}), 400

    if len(password) < 4:
        return jsonify({'error': 'Hasło musi mieć co najmniej 4 znaki'}), 400

    with session_scope() as db_session:
        # Sprawdź czy użytkownik już istnieje
        existing_user = db_session.query(User).filter_by(username=username).first()
        if existing_user:
            return jsonify({'error': 'Nazwa użytkownika jest już zajęta'}), 409

        # Tworzenie nowego użytkownika
        new_user = User(
            username=username,
            full_name=full_name,
            phone=phone,
            birth_date=birth_date_obj,
            is_admin=is_admin_flag,
            is_secretariat=is_secretariat_flag
        )
        new_user.set_password(password)

        db_session.add(new_user)

        try:
            db_session.flush()  # Nadaje ID nowemu użytkownikowi

            print(f"Admin '{session.get('username')}' zarejestrował: '{username}' (ID: {new_user.id})")

            # --- KLUCZOWA ZMIANA TUTAJ ---
            # Zwracamy user_id, aby JS mógł od razu dodać wiersz do tabeli
            return jsonify({
                'message': f'Użytkownik {username} zarejestrowany pomyślnie.',
                'user_id': new_user.id
            }), 201
            # -----------------------------

        except IntegrityError:
            db_session.rollback()
            return jsonify({'error': 'Błąd zapisu użytkownika (IntegrityError).'}), 500
        except Exception as e:
            db_session.rollback()
            print(f"Błąd rejestracji: {e}")
            import traceback
            traceback.print_exc()
            return jsonify({'error': f'Błąd serwera: {str(e)}'}), 500


@app.route('/api/admin/users/<int:user_id>', methods=['DELETE'])
@admin_required
def delete_user(user_id):
    """
    Usuwa konto użytkownika ORAZ powiązany profil Terapeuty/Kierowcy.
    """
    try:
        with session_scope() as session:
            user = session.query(User).filter_by(id=user_id).first()

            if not user:
                return jsonify({'error': 'Użytkownik nie istnieje'}), 404

            # 1. Sprawdź i usuń powiązanego TERAPEUTĘ
            if user.therapist_id:
                therapist = session.query(Therapist).filter_by(id=user.therapist_id).first()
                if therapist:
                    # Opcjonalnie: Sprawdź czy terapeuta ma historię wizyt, jeśli tak - nie usuwaj, tylko deaktywuj
                    # Ale skoro chciałeś "automatyczne usuwanie", to usuwamy:
                    session.delete(therapist)
                    print(f"Usunięto terapeutę ID: {user.therapist_id} powiązanego z userem {user.username}")

            # 2. Sprawdź i usuń powiązanego KIEROWCĘ
            if user.driver_id:
                driver = session.query(Driver).filter_by(id=user.driver_id).first()
                if driver:
                    session.delete(driver)
                    print(f"Usunięto kierowcę ID: {user.driver_id} powiązanego z userem {user.username}")

            # 3. Usuń samego UŻYTKOWNIKA
            session.delete(user)

            # Commit dzieje się automatycznie na końcu bloku with

        return jsonify({'message': 'Usunięto użytkownika i powiązane profile'}), 200

    except Exception as e:
        print(f"Błąd usuwania użytkownika: {e}")
        # Częsty błąd: Naruszenie klucza obcego (np. terapeuta ma już przypisane sesje TUS)
        if "Foreign key violation" in str(e) or "IntegrityError" in str(e):
            return jsonify({'error': 'Nie można usunąć: Ten pracownik ma już przypisane wizyty/sesje w systemie.'}), 409
        return jsonify({'error': str(e)}), 500


@admin_bp.route('/api/firma/<int:firma_id>', methods=['PUT'])
@admin_required
def handle_update_firma(firma_id):
    """Edycja istniejącej firmy/fundacji."""
    data = request.get_json()
    if not data:
        return jsonify({'error': 'Brak danych JSON'}), 400

    # --- 1. FUNKCJA POMOCNICZA (Rozwiązuje problem UNIQUE w bazie) ---
    def clean_empty(value):
        """Zamienia puste stringi na None (NULL w bazie)."""
        if isinstance(value, str) and not value.strip():
            return None
        if not value:  # np. pusta lista, 0, False
            return None
        return value

    # --- 2. LOGIKA KONWERSJI (Rozwiązuje problem błędu 500 - Typy danych) ---
    # Jeśli frontend wysyła listę (np. ['Osoba 1', 'Osoba 2']), zamieniamy na tekst z enterami.

    # Zarząd
    raw_zarzad = data.get('zarzad')
    final_zarzad = None
    if isinstance(raw_zarzad, list):
        final_zarzad = "\n".join([str(x) for x in raw_zarzad if x])
    else:
        final_zarzad = raw_zarzad

    # PKD
    raw_pkd = data.get('pkd')
    final_pkd = None
    if isinstance(raw_pkd, list):
        final_pkd = ", ".join([str(x) for x in raw_pkd if x])
    else:
        final_pkd = raw_pkd

    # Cele (dla pewności też sprawdzamy czy to nie lista)
    raw_cele = data.get('cele_statutowe')
    final_cele = raw_cele
    if isinstance(raw_cele, list):
        final_cele = "\n".join([str(x) for x in raw_cele if x])

    try:
        with session_scope() as db_session:
            # Pobranie firmy z bazy
            firma = db_session.query(Firma).get(firma_id)
            if not firma:
                return jsonify({'error': 'Nie znaleziono firmy o podanym ID'}), 404

            # Sprawdzenie unikalności NIP (tylko jeśli NIP został zmieniony)
            if 'nip' in data and data['nip'] and data['nip'] != firma.nip:
                exists = db_session.query(Firma).filter_by(nip=data['nip']).first()
                if exists:
                    return jsonify({'error': f"NIP {data['nip']} jest już zajęty przez inny podmiot."}), 409

            # --- 3. AKTUALIZACJA PÓL W BAZIE ---

            # Pola podstawowe
            if 'nazwa_pelna' in data: firma.nazwa_pelna = data['nazwa_pelna']
            if 'nazwa_skrocona' in data: firma.nazwa_skrocona = data.get('nazwa_skrocona')
            if 'nip' in data: firma.nip = data['nip']

            if 'typ' in data:
                try:
                    firma.typ = TypPodmiotuEnum[data['typ']]
                except KeyError:
                    pass  # Ignorujemy błędny typ, zostawiamy stary

            # Pola z constraintem UNIQUE (używamy clean_empty)
            if 'regon' in data: firma.regon = clean_empty(data.get('regon'))
            if 'krs' in data: firma.krs = clean_empty(data.get('krs'))
            if 'email' in data: firma.email = clean_empty(data.get('email'))

            # Adres i Kontakt
            if 'ulica' in data: firma.ulica = data.get('ulica')
            if 'numer_budynku' in data: firma.numer_budynku = data.get('numer_budynku')
            if 'numer_lokalu' in data: firma.numer_lokalu = data.get('numer_lokalu')
            if 'kod_pocztowy' in data: firma.kod_pocztowy = data.get('kod_pocztowy')
            if 'miasto' in data: firma.miasto = data.get('miasto')
            if 'telefon' in data: firma.telefon = data.get('telefon')
            if 'strona_www' in data: firma.strona_www = data.get('strona_www')

            # --- NOWE POLA (Klucz do naprawy) ---
            # Przypisujemy PRZETWORZONE zmienne (final_...), które są na pewno tekstem
            if 'zarzad' in data: firma.zarzad = final_zarzad
            if 'cele_statutowe' in data: firma.cele_statutowe = final_cele
            if 'pkd' in data: firma.pkd = final_pkd

            # Zapis zmian
            db_session.commit()
            print(f"Zaktualizowano firmę ID {firma.id}: {firma.nazwa_pelna}")

            # Zwracamy zaktualizowany obiekt
            return jsonify(firma.as_dict()), 200

    except IntegrityError as e:
        print(f"Błąd IntegrityError: {e}")
        return jsonify({'error': 'Błąd zapisu: Podany NIP, KRS, REGON lub Email jest już zajęty.'}), 409

    except Exception as e:
        print(f"Krytyczny błąd edycji: {e}")
        import traceback
        traceback.print_exc()  # To wyświetli szczegóły w konsoli serwera
        return jsonify({'error': f'Błąd serwera: {str(e)}'}), 500


@admin_bp.route('/api/firma/<int:firma_id>', methods=['DELETE'])
@admin_required
def handle_delete_firma(firma_id):
    """API Endpoint do usuwania firmy lub fundacji."""
    try:
        with session_scope() as db_session:
            firma = db_session.get(Firma, firma_id)
            if not firma:
                return jsonify({'error': 'Podmiot nie znaleziony'}), 404

            # Zapisz nazwę do logowania przed usunięciem
            nazwa = firma.nazwa_pelna

            db_session.delete(firma)
            # session_scope() automatycznie zrobi commit
            log_activity(f"Admin '{session.get('username')}' usunął firmę: {nazwa} (ID: {firma_id})")
            # print(f"Admin '{session.get('username')}' usunął firmę: {nazwa} (ID: {firma_id})")
            return jsonify({'message': 'Podmiot został pomyślnie usunięty'}), 200

    except IntegrityError as e:
        # Błąd, jeśli istnieją powiązania z tym podmiotem (np. w innych tabelach)
        print(f"Błąd IntegrityError przy usuwaniu firmy: {e}")
        return jsonify(
            {'error': 'Nie można usunąć podmiotu, ponieważ istnieją z nim powiązane dane (np. projekty, faktury).',
             'details': str(e.orig)}), 409
    except Exception as e:
        print(f"Nieoczekiwany błąd przy usuwaniu firmy: {e}")
        traceback.print_exc()
        return jsonify({'error': f'Wystąpił błąd serwera: {str(e)}'}), 500




# === GŁÓWNA STRONA APLIKACJI ===
# @app.route('/')
# @login_required
# def main_index():
#    return render_template('index.html')

@app.route('/')
def main_index():
    # 1. RĘCZNE ZABEZPIECZENIE:
    # Jeśli użytkownik nie jest zalogowany, wyrzuć go do logowania natychmiast.
    if not current_user.is_authenticated:
        return redirect(url_for('auth.login_page'))  # Upewnij się, że masz funkcję o nazwie 'login'

    # 2. Skoro przeszedł dalej, to znaczy że jest zalogowany i ma pola is_admin itp.
    return render_template('dashboard.html',
                           is_admin=current_user.is_admin,
                           is_secretariat=current_user.is_secretariat,
                           therapist_id=current_user.therapist_id,
                           driver_id=current_user.driver_id,
                           # Dodajemy też samego usera, żeby dashboard mógł używać current_user
                           current_user=current_user)


@app.route('/manager/planer-indywidualny')
@login_required  # Zakładam, że dostęp ma terapeuta/admin
def individual_planner_page():
    """Wyświetla stronę Planera Indywidualnego"""
    # Upewnij się, że stworzysz plik 'planer_indywidualny.html' w folderze templates!
    return render_template('planer_indywidualny.html')


# --- LISTA PLANÓW TERAPEUTYCZNYCH ---

@app.route('/manager/plany-lista')
@login_required
def plany_lista_page():
    """Wyświetla stronę z listą planów terapeutycznych."""
    return render_template('plany_lista.html')


@app.route('/api/clients/plans-status', methods=['GET'])
@login_required
def get_clients_plans_status():
    """
    Zwraca listę klientów ze statusem:
    - czy mają diagnozę (wymagana do AI)
    - czy mają utworzony plan terapeutyczny
    """
    try:
        with session_scope() as session:
            # Pobieramy aktywnych klientów
            clients = session.query(Client).filter_by(active=True).order_by(Client.full_name).all()

            data = []
            for c in clients:
                # Sprawdzamy czy pola nie są puste
                has_diagnosis = c.diagnosis is not None and len(str(c.diagnosis).strip()) > 5
                has_plan = c.therapeutic_plan is not None and len(str(c.therapeutic_plan).strip()) > 10

                data.append({
                    'id': c.id,
                    'full_name': c.full_name,
                    'has_diagnosis': has_diagnosis,
                    'has_plan': has_plan,
                    # Opcjonalnie: data aktualizacji, jeśli dodasz takie pole w przyszłości
                })

            return jsonify(data), 200

    except Exception as e:
        print(f"Błąd pobierania statusów planów: {e}")
        return jsonify({'error': str(e)}), 500


@app.route('/manager/plan-terapeutyczny')
@login_required
def plan_terapeutyczny_view():
    return render_template('plan_terapeutyczny.html')


# --- ROUTE DO KARTY PRZYJĘCIA ---
@app.route('/manager/admission')
@login_required
def admission_form():
    """
    Wyświetla formularz Karty Przyjęcia.
    Moduł ogólnodostępny dla każdego zalogowanego użytkownika.
    """
    return render_template('admission.html')


@app.route('/planer_miesieczny')
@login_required
def planer_miesieczny_page():
    return render_template('planer_miesieczny.html')


@app.route('/manager/planer-masowy')  # Używamy ścieżki /manager/..., żeby było porządnie
@login_required
def mass_planner_page():
    """Wyświetla stronę Planera Masowego AI"""
    return render_template('planer_masowy.html')


@app.route('/klient_panel/clients')
@login_required  # Zabezpieczamy - tylko terapeuta lub admin
def clients_page():
    """Wyświetla stronę 'clients.html'"""
    return render_template('klienci.html')


@app.route('/schedule')
@login_required  # Zabezpieczamy
def schedule_page():
    """Wyświetla stronę 'panel-terapeuty.html'"""
    return render_template('panel-terapeuty.html')


@app.route('/klient_panel')
@login_required  # Zabezpieczamy
def klient_panel():
    """Wyświetla stronę 'klient-panel.html'"""
    return render_template('klient-panel.html')


@app.route('/tus')
@login_required  # Zabezpieczamy
def tus_page():
    """Wyświetla stronę 'tus.html'"""
    return render_template('tus.html')


@app.route('/manager/projects')
@login_required  # Zabezpieczamy
def projects_page():
    """Wyświetla stronę 'projects.html'"""
    return render_template('projects.html')

@app.route('/manager/project_raports')
@login_required  # Zabezpieczamy
def project_raports():
    """Wyświetla stronę 'project_raports.html'"""
    return render_template('project_raports.html')


@app.route('/manager/uchwaly', methods=['GET'])
@login_required
def resolutions_page():
    """Wyświetla stronę zarządzania uchwałami"""
    return render_template('board_resolutions.html')


@app.route('/driver-schedule-page')
@driver_required
def driver_schedule_page():
    # Sprawdzamy, czy użytkownik ma prawo zarządzać innymi (Admin/Sekretariat/Logistyk)
    # Logistyk to ktoś, kto ma uprawnienie 'drivers', ale NIE jest kierowcą
    can_manage = False

    if current_user.is_admin or current_user.is_secretariat:
        can_manage = True
    elif current_user.has_permission('drivers'):  # Logistyk
        can_manage = True

    return render_template(
        'kierowcy.html',
        is_driver_profile=(current_user.driver_id is not None),
        can_manage=can_manage
    )


@app.route('/manager')
@login_required  # Dostęp dla admina i terapeutów (lub zmień na @admin_required)
def manager_page():
    """Wyświetla stronę 'manager.html'"""
    return render_template('manager.html')


@app.route('/manager/sprawozdania')
@login_required  # Dostęp dla admina i terapeutów (lub zmień na @admin_required)
def sprawozdania_new():
    """Wyświetla stronę 'sprawozdania.html'"""
    return render_template('sprawozdania.html')


@app.route('/manager/ipet')
@login_required  # Dostęp dla admina i terapeutów (lub zmień na @admin_required)
def ipet():
    if not current_user.is_admin and not current_user.has_permission('ipet'):
        flash('Brak uprawnień do tego modułu.')
        return redirect(url_for('manager_page'))  # or main_index

    return render_template('ipet.html')

@app.route('/manager/kadry')
@login_required  # Dostęp dla admina i terapeutów (lub zmień na @admin_required)
def kadry():
    if not current_user.is_admin and not current_user.has_permission('ipet'):
        flash('Brak uprawnień do tego modułu.')
        return redirect(url_for('manager_page'))  # or main_index

    return render_template('kadry.html')

@app.route('/api/clients/<int:client_id>/generate-ipet-document', methods=['POST'])
@login_required
def save_ipet_document(client_id):
    try:
        # 1. Odbieramy dane wysłane z formularza na frontendzie (z JavaScriptu)
        data = request.get_json()
        
        if not data:
            return jsonify({'error': 'Brak danych IPET do zapisania.'}), 400

        # --- TUTAJ BĘDZIE LOGIKA ZAPISU DO BAZY ---
        # Np. new_ipet = IpetDocument(client_id=client_id, tresc=data.get('tresc'))
        # session.add(new_ipet)
        # session.commit()
        
        # Na ten moment po prostu udajemy, że zapis się udał, żeby frontend przestał sypać błędami
        print(f"Otrzymano IPET dla klienta ID {client_id}: {data}")

        # 2. Zwracamy czysty JSON z potwierdzeniem sukcesu
        return jsonify({'success': True, 'message': 'IPET został poprawnie zapisany!'}), 200

    except Exception as e:
        print(f"Krytyczny błąd podczas zapisu IPET: {e}")
        return jsonify({'error': 'Wystąpił błąd serwera podczas zapisywania IPET-u.'}), 500


@app.route('/manager/finanse')
@login_required  # Dostęp dla admina i terapeutów (lub zmień na @admin_required)
def finance():
    if not current_user.is_admin and not current_user.has_permission('finance'):
        flash('Brak uprawnień do tego modułu.')
        return redirect(url_for('manager_page'))  # or main_index

    return render_template('finance.html')


@app.route('/poczekalnia')
@secretariat_required  # Dostęp dla admina i terapeutów
def waiting_list_page():
    if not current_user.is_admin and not current_user.has_permission('poczekalnia'):
        flash('Brak uprawnień do tego modułu.')
        return redirect(url_for('manager_page'))  # or main_index

    return render_template('poczekalnia.html')


# @app.route('/terapeuta')
# @login_required  # Dostęp dla admina i terapeutów
# def terapeuta():
#    """Wyświetla stronę 'terapeuta.html'"""
#    return render_template('terapeuta.html')


@app.route('/klient_panel/dziennik')
@login_required  # Dostęp dla admina i terapeutów
# @secretariat_required
def dziennik():
    if not current_user.is_admin and not current_user.has_permission('dziennik'):
        flash('Brak uprawnień do tego modułu.')
        return redirect(url_for('klient_panel'))  # or main_index

    return render_template('dziennik3.html')


# W app.py
@app.route('/admin/drivers')
@admin_required
def admin_drivers_page():
    current_firma_id = session.get('firma_id', 1)
    
    with session_scope() as db_session:
        # DODAJ FILTR!
        drivers = db_session.query(Driver).filter_by(
            firma_id=current_firma_id
        ).order_by(Driver.full_name).all()
        
        return render_template('admin_drivers.html', drivers=drivers)


@app.route('/klient_panel/lista_zestawienie')
@login_required  # Dostęp dla admina i terapeutów
# @secretariat_required
def lista_zestawienie():
    if not current_user.is_admin and not current_user.has_permission('lista_zestawienia'):
        flash('Brak uprawnień do tego modułu.')
        return redirect(url_for('klient_panel'))  # or main_index

    return render_template('dziennik1.html')


@app.route('/klient_panel/historia')
@login_required  # Dostęp dla admina i terapeutów
def historia():
    if not current_user.is_admin and not current_user.has_permission('historia'):
        flash('Brak uprawnień do tego modułu.')
        return redirect(url_for('klient_panel'))  # or main_index

    return render_template('client_history.html')


@app.route('/grafik')
@login_required  # Dostęp dla admina i terapeutów
# @secretariat_required
def grafik():
    if not current_user.is_admin and not current_user.has_permission('grafik'):
        flash('Brak uprawnień do tego modułu.')
        return redirect(url_for('main_index'))  # or main_index

    return render_template('grafik.html')


@app.route('/klient_panel/indywidual-attendance')
@login_required  # Dostęp dla admina i terapeutów
def indywidual_attendance():
    if not current_user.is_admin and not current_user.has_permission('indywidual_attendance'):
        flash('Brak uprawnień do tego modułu.')
        return redirect(url_for('klient_panel'))  # or main_index

    return render_template('client-attendance.html')


@app.route('/klient_panel/lista')
@login_required  # Wymaga terapeuty LUB admina/sekretariatu
# @secretariat_required
def lista():
    if not current_user.is_admin and not current_user.has_permission('lista'):
        flash('Brak uprawnień do tego modułu.')
        return redirect(url_for('klient_panel'))  # or main_index

    return render_template('lista.html')


@app.route('/klient_panel/notes')
@login_required  # Dostęp dla admina i terapeutów
def notes():
    if not current_user.is_admin and not current_user.has_permission('notes'):
        flash('Brak uprawnień do tego modułu.')
        return redirect(url_for('klient_panel'))  # or main_index

    return render_template('notes.html')


@app.route('/klient_panel/client_panel_grafik')
@login_required  # Dostęp dla admina i terapeutów (lub zmień na @admin_required)
def client_panel_grafik():
    if not current_user.is_admin and not current_user.has_permission('client_panel_grafik'):
        flash('Brak uprawnień do tego modułu.')
        return redirect(url_for('manager_page'))  # or main_index

    return render_template('client-panel.html')


@app.route('/klient_panel/client_panel')
@login_required  # Dostęp dla admina i terapeutów
def client_panel():
    if not current_user.is_admin and not current_user.has_permission('client_panel'):
        flash('Brak uprawnień do tego modułu.')
        return redirect(url_for('klient_panel'))  # or main_index

    return render_template('klient-panel.html')


# @app.route('/panel-terapeuty')
# @login_required  # Dostęp dla admina i terapeutów
# def panel_terapeuty():
#    """Wyświetla stronę 'panel-terapeuty.html'"""
#    return render_template('panel-terapeuty.html')

@app.route('/terapeuta-panel')
@login_required  # Dostęp dla admina i terapeutów
def terapeuta_panel():
    """Wyświetla stronę 'terapeuta-panel.html'"""
    return render_template('terapeuta-panel.html')


@app.route('/terapeuta-panel/terapeuta')
@login_required  # Dostęp dla admina i terapeutów
def terapeuta():
    """Wyświetla stronę 'terapeuta.html'"""
    return render_template('terapeuta.html')


@app.route('/terapeuta-panel/terapeuci-lista')
@login_required  # lub inne uprawnienie
def terapeuta_page():
    """Wyświetla stronę zarządzania terapeutami"""
    return render_template('terapeuta_lista.html')


# --- 1. TWORZENIE NOWEJ KARTY (POST) ---
@app.route('/api/admission', methods=['POST'])
@login_required
def save_new_admission_card():
    data = request.get_json()
    full_name = data.get('full_name', '').strip()
    
    try:
        with session_scope() as session:
            # Sprawdzenie czy pacjent o takim nazwisku już istnieje
            existing = session.query(Client).filter(func.lower(Client.full_name) == full_name.lower()).first()
            if existing:
                return jsonify({'error': f"Pacjent '{full_name}' już figuruje w systemie. Użyj edycji w panelu 'Klienci'."}), 409

            # Tworzenie nowego obiektu Client ze wszystkimi polami z karty
            new_client = Client(
                full_name=full_name,
                birth_date=datetime.strptime(data['birth_date'], '%Y-%m-%d').date() if data.get('birth_date') else None,
                age=int(data.get('age')) if data.get('age') else None,
                parents_names=data.get('parents_names'),
                phone=data.get('phone'),
                address=data.get('address'),
                diagnosis=data.get('diagnosis'),
                medications=data.get('medications'),
                school_name=data.get('school_name'),
                school_contact=data.get('school_contact'),
                admission_notes=data.get('notes'), # Mapowanie HTML 'notes' -> DB 'admission_notes'
                admission_date=datetime.strptime(data['admission_date'], '%Y-%m-%d').date() if data.get('admission_date') else None,
                admission_scope=data.get('admission_scope'),
                initial_plan=data.get('initial_plan'),
                assigned_therapists=data.get('assigned_therapists'),
                active=True
            )
            session.add(new_client)
            session.flush()
            new_id = new_client.id
            
            log_activity("NOWA_KARTA", f"Utworzono kartę przyjęcia dla: {full_name}")
            
        return jsonify({'success': True, 'message': 'Karta została zapisana.', 'client_id': new_id}), 201

    except Exception as e:
        print(f"Błąd POST admission: {e}")
        return jsonify({'error': str(e)}), 500


# --- 2. POBIERANIE I AKTUALIZACJA ISTNIEJĄCEJ KARTY (GET / PUT) ---
@app.route('/api/clients/<int:client_id>/admission', methods=['GET', 'PUT'])
@login_required
def handle_client_admission_card(client_id):
    """Pobiera lub aktualizuje szczegóły Karty Przyjęcia (Wywiadu) dla istniejącego klienta."""
    try:
        with session_scope() as db_session:
            client = db_session.get(Client, client_id)
            if not client:
                return jsonify({'error': 'Klient nie istnieje'}), 404

            # --- POBIERANIE DANYCH DO FORMULARZA ---
            if request.method == 'GET':
                return jsonify({
                    'full_name': client.full_name,
                    'birth_date': client.birth_date.isoformat() if client.birth_date else '',
                    'age': client.age,
                    'parents_names': client.parents_names,
                    'phone': client.phone,
                    'address': client.address,
                    'diagnosis': client.diagnosis,
                    'medications': client.medications,
                    'school_name': client.school_name,
                    'school_contact': client.school_contact,
                    'notes': client.admission_notes, # Mapowanie na HTML
                    'admission_date': client.admission_date.isoformat() if client.admission_date else '',
                    'admission_scope': client.admission_scope,
                    'initial_plan': client.initial_plan,
                    'assigned_therapists': client.assigned_therapists
                }), 200

            # --- AKTUALIZACJA DANYCH ---
            if request.method == 'PUT':
                data = request.get_json()
                print(f"--- DEBUG ZAPISU KARTY --- Otrzymane dane: {data}")

                # Funkcja pomocnicza: zamienia puste stringi "" na None
                def clean_str(val):
                    return val.strip() if val and str(val).strip() else None

                client.full_name = clean_str(data.get('full_name')) or client.full_name
                
                # Bezpieczne ładowanie WIEKU (Integer)
                raw_age = data.get('age')
                client.age = int(raw_age) if raw_age and str(raw_age).strip() else None

                # Bezpieczne ładowanie DAT (Date)
                raw_bdate = data.get('birth_date')
                client.birth_date = datetime.strptime(raw_bdate, '%Y-%m-%d').date() if raw_bdate and raw_bdate.strip() else None
                
                raw_adate = data.get('admission_date')
                client.admission_date = datetime.strptime(raw_adate, '%Y-%m-%d').date() if raw_adate and raw_adate.strip() else None

                # Bezpieczne ładowanie TEKSTÓW (String/Text)
                client.parents_names = clean_str(data.get('parents_names'))
                client.phone = clean_str(data.get('phone'))
                client.address = clean_str(data.get('address'))
                client.diagnosis = clean_str(data.get('diagnosis'))
                client.medications = clean_str(data.get('medications'))
                client.school_name = clean_str(data.get('school_name'))
                client.school_contact = clean_str(data.get('school_contact'))
                client.admission_notes = clean_str(data.get('notes')) # Ważne: z HTML przychodzi jako 'notes'
                client.admission_scope = clean_str(data.get('admission_scope'))
                client.initial_plan = clean_str(data.get('initial_plan'))
                client.assigned_therapists = clean_str(data.get('assigned_therapists'))

                # Logowanie (jeśli używasz)
                try:
                    log_activity("EDYCJA_KARTY", f"Zaktualizowano kartę dla: {client.full_name}")
                except:
                    pass

                return jsonify({'success': True, 'message': 'Karta została zaktualizowana.'}), 200

    except Exception as e:
        print(f"Błąd zapisu karty przyjęcia: {e}")
        import traceback
        traceback.print_exc()
        return jsonify({'error': str(e)}), 500



@app.route('/terapeuta-panel/import_image', methods=['GET'])
@login_required
def import_image():
    """Strona importu planu z obrazka (Wersja oparta na sesji)"""

    # 1. Pobieramy dane bezpośrednio z sesji (Twoje logowanie tam je zapisuje)
    user_id = session.get('user_id')
    username = session.get('username', 'Użytkownik')
    is_admin = session.get('is_admin', False)

    # 2. Sprawdzamy role na podstawie ID w sesji
    # (handle_login już zapisał te ID w sesji)
    therapist_id = session.get('therapist_id')
    driver_id = session.get('driver_id')

    is_therapist = (therapist_id is not None)
    is_driver = (driver_id is not None)

    # Admin ma dostęp do wszystkiego
    if is_admin:
        is_therapist = True
        is_driver = True

    # 3. Tworzymy "fałszywy" obiekt current_user dla szablonu HTML
    # Szablon oczekuje obiektu, który ma pole .full_name lub .username
    class SessionUser:
        def __init__(self, uid, name, admin):
            self.id = uid
            self.full_name = name  # Frontend używa full_name
            self.username = name
            self.is_admin = admin
            self.is_authenticated = True

    user_obj = SessionUser(user_id, username, is_admin)

    # 4. Renderujemy szablon
    return render_template(
        'import_image.html',
        current_user=user_obj,  # Przekazujemy nasz obiekt zamiast Flask-Login
        is_admin=is_admin,
        is_therapist=is_therapist,
        is_driver=is_driver
    )


'''@app.route('/terapeuta-panel/import_image')
@login_required  # Dostęp dla admina i terapeutów
def import_image():
    """Wyświetla stronę 'import_image.html'"""
    return render_template('import_image.html')'''


@app.route('/klient_panel/panel')
@login_required  # Dostęp dla admina i terapeutów
def panel():
    """Wyświetla stronę 'panel.html'"""
    return render_template('panel.html')





@app.route('/manager/raport')
@login_required  # Dostęp dla admina i terapeutów
def raport():
    """Wyświetla stronę 'raport.html'"""
    return render_template('raport.html')


@app.route('/manager/raport_new')
@login_required  # Dostęp dla admina i terapeutów
def raport_new():
    """Wyświetla stronę 'raport.html'"""
    return render_template('raport_new.html')


@app.route('/manager/diagnoza')
@login_required  # Dostęp dla admina i terapeutów
def diagnoza():
    """Wyświetla stronę 'diagnoza.html'"""
    return render_template('diagnoza.html')


@app.route('/manager/diagnoza_list')
@login_required  # Dostęp dla admina i terapeutów
def diagnoza_list_page():
    """Wyświetla stronę 'diagnoza.html'"""
    return render_template('diagnoza_list.html')


@app.route('/client-attendance')
@login_required  # Dostęp dla admina i terapeutów
def client_attendance():
    """Wyświetla stronę 'client-attendance.html'"""
    return render_template('client-attendance.html')


@app.route('/klient_panel/client_history')
@login_required  # Dostęp dla admina i terapeutów
def client_history():
    """Wyświetla stronę 'client_history.html'"""
    return render_template('client_history.html')


@app.route('/klient_panel/dostepnosc')
@login_required  # Dostęp dla admina i terapeutów
def dostepnosc():
    """Wyświetla stronę 'dostepnosc.html'"""
    return render_template('dostepnosc.html')


# === ⭐️ REJESTRACJA NOWEGO ENDPOINTU AI ⭐️ ===
# @app.route('/api/v1/ai-plan-schedule', methods=['POST'])
# def ai_plan_schedule_route():
#    # Po prostu przekaż kontrolę do naszego handlera
#    return handle_plan_request()


# koniec


if not DATABASE_URL:
    raise ValueError("DATABASE_URL environment variable is not set!")
# GOOGLE_MAPS_API_KEY = os.getenv("klucz")

# === DODAJ TĘ LINIĘ DIAGNOSTYCZNĄ ===
print(f"--- APLIKACJA ŁĄCZY SIĘ Z BAZĄ DANYCH: {DATABASE_URL} ---")
# ====================================

# === INICJALIZACJA BAZY DANYCH (ORM) ===
engine = create_engine(DATABASE_URL, future=True)

# UWAGA: Base i SessionLocal sa zdefiniowane raz, przy pierwszym polaczeniu do bazy.
# Druga rejestracja declarative_base() rozbijala modele na dwa osobne rejestry
# i lamala relationship() miedzy nimi (np. FirmaSettings -> Firma) oraz sprawiala,
# ze init_all_tables() nie tworzyla tabel zdefiniowanych przed ta linia.
SessionLocal = scoped_session(
    sessionmaker(bind=engine, autocommit=False, autoflush=False, expire_on_commit=False, future=True)
)

# Konfiguracja PostgreSQL - DOSTOSUJ DO SWOICH DANYCH
DB_CONFIG = {
    'host': 'localhost',
    'port': 5432,
    'database': 'odnowa_unwh',  # <-- ZMIEŃ
    'user': 'odnowa_unwh_user',  # <-- ZMIEŃ
    'password': 'hr5g2iWpbfxi8Z5ZKBT0PUVQqhuvPAnd'  # <-- ZMIEŃ
}


# Funkcja pomocnicza do walidacji daty
def validate_date(date_string, field_name):
    """Waliduje format daty"""
    try:
        datetime.fromisoformat(date_string)
        return None
    except (ValueError, TypeError):
        return f'Nieprawidłowy format daty w polu {field_name}'


def validate_length(value, field_name, max_length):
    """Waliduje długość tekstu"""
    if value and len(value) > max_length:
        return f'{field_name} zbyt długie (max {max_length} znaków)'
    return None


def calculate_distance(lat1, lon1, lat2, lon2):
    """Oblicza dystans w km. Jeśli brak danych, zwraca 'nieskończoność'."""
    if lat1 and lon1 and lat2 and lon2:
        try:
            return geodesic((lat1, lon1), (lat2, lon2)).kilometers
        except ValueError:
            return 9999  # Błędne dane
    return 9999  # <--- ZMIANA: Zwracamy dużą liczbę, żeby nie grupować "pustych" klientów razem


def get_db_connection():
    """Tworzy połączenie z bazą PostgreSQL"""
    try:
        if DATABASE_URL:
            # Wyłącz SSL dla połączenia lokalnego
            conn = psycopg2.connect(DATABASE_URL, sslmode='disable')
        else:
            # Fallback na lokalne połączenie
            conn = psycopg2.connect(
                host='localhost',
                port=5432,
                database='suo',
                user='postgres',
                password='EDUQ',
                sslmode='disable'  # Wyłącz SSL
            )

        conn.cursor_factory = RealDictCursor
        return conn
    except Exception as e:
        print(f"Błąd połączenia z bazą: {e}")
        raise


def init_resolutions_table():
    """Inicjalizacja tabeli uchwał zarządu"""
    with engine.begin() as conn:
        conn.execute(text('''
                CREATE TABLE IF NOT EXISTS board_resolutions (
                    id SERIAL PRIMARY KEY,
                    title VARCHAR(255) NOT NULL,
                    resolution_date DATE NOT NULL,
                    description TEXT,
                    file_path VARCHAR(500),
                    file_name VARCHAR(255),
                    created_at TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP,
                    updated_at TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP
                )
            '''))

        # Indeks dla szybszego sortowania po dacie
        conn.execute(text('''
                CREATE INDEX IF NOT EXISTS idx_resolutions_date 
                ON board_resolutions(resolution_date)
            '''))

    print("✓ Tabela board_resolutions zainicjalizowana")


def init_journal_table():
    """Inicjalizacja tabeli dziennik"""
    with engine.begin() as conn:
        conn.execute(text('''
                CREATE TABLE IF NOT EXISTS dziennik (
                    id SERIAL PRIMARY KEY,
                    data DATE NOT NULL,
                    client_id INTEGER NOT NULL REFERENCES clients(id) ON DELETE RESTRICT,
                    therapist_id INTEGER NOT NULL REFERENCES therapists(id) ON DELETE RESTRICT,
                    temat VARCHAR(255),
                    cele TEXT,
                    created_at TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP,
                    updated_at TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP
                )
            '''))
    print("✓ Tabela dziennik zainicjalizowana")


def init_client_notes_table():
    """Inicjalizacja tabeli notatek klientów"""
    with engine.begin() as conn:
        conn.execute(text('''
                CREATE TABLE IF NOT EXISTS client_notes (
                    id SERIAL PRIMARY KEY,
                    client_id INTEGER NOT NULL,
                    content TEXT NOT NULL,
                    category VARCHAR(50) NOT NULL DEFAULT 'general',
                    created_by_name VARCHAR(255) NOT NULL,
                    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                    FOREIGN KEY (client_id) REFERENCES clients(id) ON DELETE CASCADE
                )
            '''))

        conn.execute(text('''
                CREATE INDEX IF NOT EXISTS idx_client_notes_client_id 
                ON client_notes(client_id)
            '''))

        conn.execute(text('''
                CREATE INDEX IF NOT EXISTS idx_client_notes_category 
                ON client_notes(category)
            '''))

    print("✓ Tabela client_notes zainicjalizowana")


# 1. Najpierw dodaj funkcję inicjalizacji tabeli (wywołaj przy starcie)
def init_waiting_clients_table():
    """Inicjalizacja tabeli klientów oczekujących"""
    with engine.begin() as conn:
        conn.execute(text('''
                CREATE TABLE IF NOT EXISTS waiting_clients (
                    id SERIAL PRIMARY KEY,
                    first_name VARCHAR(100) NOT NULL,
                    last_name VARCHAR(100) NOT NULL,
                    birth_date DATE NOT NULL,
                    diagnosis TEXT,
                    registration_date DATE NOT NULL DEFAULT CURRENT_DATE,
                    notes TEXT,
                    status VARCHAR(50) DEFAULT 'oczekujący',
                    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
                )
            '''))

        conn.execute(text('''
                CREATE INDEX IF NOT EXISTS idx_waiting_clients_status 
                ON waiting_clients(status)
            '''))

        conn.execute(text('''
                CREATE INDEX IF NOT EXISTS idx_waiting_clients_registration 
                ON waiting_clients(registration_date)
            '''))

    print("✓ Tabela waiting_clients zainicjalizowana")


# DODAJ TEN ENDPOINT:
@app.route('/uploads/<path:filename>')
def serve_upload(filename):
    """Serwuje uploadowane pliki"""
    uploads_dir = os.path.join(os.getcwd(), 'uploads')
    return send_from_directory(uploads_dir, filename)




def allowed_file(filename):
    return '.' in filename and filename.rsplit('.', 1)[1].lower() in ALLOWED_EXTENSIONS


def get_safe_filepath(client_id, filename):
    client_folder = os.path.join(UPLOAD_FOLDER, str(client_id))
    os.makedirs(client_folder, exist_ok=True)

    timestamp = datetime.now().strftime('%Y%m%d_%H%M%S')
    safe_name = secure_filename(filename)
    name, ext = os.path.splitext(safe_name)
    unique_filename = f"{name}_{timestamp}{ext}"

    return os.path.join(client_folder, unique_filename)


class TypPodmiotuEnum(enum.Enum):
    firma = 'firma'
    fundacja = 'fundacja'
    stowarzyszenie = 'stowarzyszenie'
    inna = 'inna'
    


class PaidService(Base):
    __tablename__ = 'paid_services'
    id = Column(Integer, primary_key=True)
    name = Column(String(255), nullable=False)  # np. "Terapia Indywidualna - Pakiet"
    price = Column(Float, nullable=False, default=0.0)
    active = Column(Boolean, default=True)
    firma_id = Column(Integer, ForeignKey('firma.id', ondelete="CASCADE"),  nullable=False)


class PaidRecord(Base):
    __tablename__ = 'paid_records'
    id = Column(Integer, primary_key=True)
    client_id = Column(Integer, ForeignKey('clients.id', ondelete="CASCADE"), nullable=False)
    service_id = Column(Integer, ForeignKey('paid_services.id'), nullable=True)  # Opcjonalne powiązanie z cennikiem

    amount = Column(Float, nullable=False, default=0.0)
    payment_date = Column(Date, nullable=False)  # KLUCZOWE POLE
    description = Column(String(255))  # Np. "Czesne styczeń"
    firma_id = Column(Integer, ForeignKey('firma.id', ondelete="CASCADE"),  nullable=False)

    created_at = Column(DateTime, server_default=func.now())

    # Relacje
    client = relationship("Client")
    service = relationship("PaidService")


class Firma(Base):
    __tablename__ = 'firma'

    # Klucz główny
    id = Column(Integer, primary_key=True)
    

    # Typ podmiotu (używa ENUM)
    # SQLAlchemy automatycznie zmapuje to do typu 'typ_podmiotu' w Postgres
    typ = Column(Enum(TypPodmiotuEnum, name="typ_podmiotu"), nullable=False)

    # Podstawowe dane identyfikacyjne
    nazwa_pelna = Column(String(255), nullable=False)
    nazwa_skrocona = Column(String(100))

    # Numery rejestrowe
    nip = Column(String(10), nullable=False, unique=True)
    regon = Column(String(14), unique=True)
    krs = Column(String(10), unique=True)

    # Dane adresowe
    ulica = Column(String(255))
    numer_budynku = Column(String(10))
    numer_lokalu = Column(String(10))
    kod_pocztowy = Column(String(6), nullable=False)
    miasto = Column(String(100), nullable=False)
    kraj = Column(String(100), default='Polska')

    # Dane kontaktowe
    email = Column(String(255), unique=True)
    telefon = Column(String(30))
    strona_www = Column(String(255))
    zarzad = Column(Text, nullable=True)
    cele_statutowe = Column(Text, nullable=True)
    pkd = Column(Text, nullable=True)

    adres_dodatkowy_ulica = Column(String(255), nullable=True)
    adres_dodatkowy_numer = Column(String(50), nullable=True)
    adres_dodatkowy_kod = Column(String(20), nullable=True)
    adres_dodatkowy_miasto = Column(String(100), nullable=True)

    # Metadane
    data_utworzenia = Column(DateTime(timezone=True), server_default=func.now())
    data_aktualizacji = Column(DateTime(timezone=True), onupdate=func.now())

    # Funkcja pomocnicza do konwersji obiektu na słownik (dla JSON)
    def as_dict(self):
        return {
            'id': self.id,
            'typ': self.typ.name if self.typ else None,  # Zwróć nazwę enum
            'nazwa_pelna': self.nazwa_pelna,
            'nazwa_skrocona': self.nazwa_skrocona,
            'nip': self.nip,
            'regon': self.regon,
            'krs': self.krs,
            'ulica': self.ulica,
            'numer_budynku': self.numer_budynku,
            'numer_lokalu': self.numer_lokalu,
            'kod_pocztowy': self.kod_pocztowy,
            'miasto': self.miasto,
            'kraj': self.kraj,
            'email': self.email,
            'telefon': self.telefon,
            'strona_www': self.strona_www,
            'data_utworzenia': self.data_utworzenia.isoformat() if self.data_utworzenia else None,
            'zarzad': self.zarzad,
            'cele_statutowe': self.cele_statutowe,
            'pkd': self.pkd,
            'adres_dodatkowy_ulica': self.adres_dodatkowy_ulica,
            'adres_dodatkowy_numer': self.adres_dodatkowy_numer,
            'adres_dodatkowy_kod': self.adres_dodatkowy_kod,
            'adres_dodatkowy_miasto': self.adres_dodatkowy_miasto
        }


class TUSSessionAttendance(Base):
    __tablename__ = 'tus_session_attendance'
    id = Column(Integer, primary_key=True)
    session_id = Column(Integer, ForeignKey('tus_sessions.id', ondelete="CASCADE"), nullable=False)
    client_id = Column(Integer, ForeignKey('clients.id', ondelete="CASCADE"), nullable=False)
    status = Column(String, nullable=False, default='obecny')  # np. obecny, nieobecny, spóźniony, usprawiedliwiony
    firma_id = Column(Integer, ForeignKey('firma.id', ondelete="CASCADE"),  nullable=False)
    __table_args__ = (UniqueConstraint('session_id', 'client_id'),)


class SuoAllocation(Base):
    __tablename__ = 'suo_allocations'

    # === POPRAWIONA DEFINICJA (ODZWIERCIEDLA STRUKTURĘ DB) ===
    # 1. Klucz główny: id (jak w bazie)
    id = Column(Integer, primary_key=True)

    # 2. Klucze danych (nie są już kluczami głównymi w sensie ORM)
    client_id = Column(Integer, ForeignKey('clients.id'), nullable=False)
    month_key = Column(String(7), nullable=False)  # Zmieniono na String(7) / TEXT
    minutes_quota = Column(Integer, nullable=False)
    firma_id = Column(Integer, ForeignKey('firma.id', ondelete="CASCADE"),  nullable=False)
    # 3. Dodano ograniczenie unikalności (jak w bazie)
    __table_args__ = (
        UniqueConstraint('client_id', 'month_key'),
        CheckConstraint('minutes_quota >= 0', name='suo_allocations_minutes_quota_check')
    )


class IndividualSessionAttendance(Base):
    __tablename__ = 'individual_session_attendance'
    id = Column(Integer, primary_key=True)
    slot_id = Column(Integer, ForeignKey('schedule_slots.id', ondelete="CASCADE"), nullable=False, unique=True)
    status = Column(String, nullable=False, default='obecny')
    firma_id = Column(Integer, ForeignKey('firma.id', ondelete="CASCADE"),  nullable=False)

class Client(Base):
    __tablename__ = 'clients'
    id = Column(Integer, primary_key=True)
    full_name = Column(String, nullable=False, unique=True)
    phone = Column(String)
    address = Column(String)
    active = Column(Boolean, default=True, nullable=False)

    # NOWE POLA Z KARTY PRZYJĘCIA:
    birth_date = Column(Date)  # Data urodzenia
    age = Column(Integer)  # Wiek (Lat)
    parents_names = Column(String(255))  # Imiona rodziców

    # Dane medyczne/edukacyjne
    diagnosis = Column(Text)  # Rozpoznanie choroby
    medications = Column(Text)  # Przyjmowane leki
    school_name = Column(String(255))  # Placówka
    school_contact = Column(String(255))  # Telefony do szkoły (nauczyciel/dyrektor)

    # Dane fundacyjne
    admission_date = Column(Date)  # Data przyjęcia do fundacji
    admission_scope = Column(String(255))  # Przyjęcie w ramach (NFZ/Projekt/Inne)
    admission_notes = Column(Text)  # Uwagi (z przodu karty)
    diagnosis_file_path = Column(String(500), nullable=True)
    therapeutic_plan = Column(Text)
    firma_id = Column(Integer, ForeignKey('firma.id', ondelete="CASCADE"), nullable=False)

    # Tył karty
    initial_plan = Column(Text)  # Wstępne założenia do planu
    assigned_therapists = Column(Text)
    is_paid = Column(Boolean, default=False)  # Czy działalność odpłatna?
    paid_service_id = Column(Integer, ForeignKey('paid_services.id'), nullable=True)

    # Relacja (żeby łatwo pobierać nazwę usługi i cenę)
    paid_service = relationship("PaidService")

    # Możesz też dodać te, jeśli masz je w bazie, ale 'full_name' wystarczy
    # first_name = Column(String(100))
    # last_name = Column(String(100))
    # --- KONIEC DODAWANIA ---
    latitude = Column(Float, nullable=True)
    longitude = Column(Float, nullable=True)

    group_associations = relationship("TUSGroupMember", back_populates="client", cascade="all, delete-orphan")
    public_token = Column(String(36), unique=True, nullable=True)

class ClientReport(Base):
    __tablename__ = 'client_reports'
    id = Column(Integer, primary_key=True)
    client_id = Column(Integer, ForeignKey('clients.id', ondelete="CASCADE"), nullable=False)
    content = Column(Text, nullable=False)
    period = Column(String(50))
    created_at = Column(DateTime, default=datetime.utcnow)
    firma_id = Column(Integer, ForeignKey('firma.id', ondelete="CASCADE"), nullable=False)

class ClientUnavailability(Base):
    __tablename__ = 'client_unavailability'

    id = Column(Integer, primary_key=True)
    client_id = Column(Integer, ForeignKey('clients.id'), nullable=False)
    day_of_week = Column(String(20), nullable=False)  # np. 'Monday', 'Tuesday'
    start_time = Column(Time, nullable=False)
    end_time = Column(Time, nullable=False)
    firma_id = Column(Integer, ForeignKey('firma.id', ondelete="CASCADE"),  nullable=False)

    # Opcjonalnie relacja, jeśli chcesz mieć dostęp z poziomu klienta
    # client = relationship("Client", back_populates="unavailabilities")


class Therapist(Base):
    __tablename__ = 'therapists'
    id = Column(Integer, primary_key=True)
    full_name = Column(String, nullable=False, unique=True)
    specialization = Column(String)
    email = Column(String)
    phone = Column(String)
    active = Column(Boolean, default=True, nullable=False)
    firma_id = Column(Integer, ForeignKey('firma.id', ondelete="CASCADE"), nullable=False)
    tus_groups = relationship(
        "TUSGroup",
        foreign_keys="[TUSGroup.therapist_id]",  # <-- DODAJ TĘ LINIĘ
        back_populates="therapist",
        lazy="selectin"
    )


class Absence(Base):
    """Tabela nieobecności (teraz uniwersalna dla Terapeutów i Kierowców)"""
    __tablename__ = 'absences'

    id = Column(Integer, primary_key=True)

    # ZMIANA: Zamiast therapist_id mamy teraz person_id
    person_id = Column(Integer, nullable=False)

    # ZMIANA: Dodajemy typ osoby (therapist/driver)
    person_type = Column(String(50), default='therapist', nullable=False)

    start_date = Column(Date, nullable=False)
    end_date = Column(Date, nullable=False)
    reason = Column(String(50))
    comment = Column(String(255), nullable=True)

    # Nowe pola (opcjonalne, jeśli dodałeś je w SQL)
    status = Column(String(20), default='approved')
    cancellation_note = Column(Text, nullable=True)
    firma_id = Column(Integer, ForeignKey('firma.id', ondelete="CASCADE"),  nullable=False)

    # UWAGA: Usunęliśmy sztywną relację ForeignKey('therapists.id'),
    # bo person_id może teraz wskazywać też na tabelę drivers.
    # Relacje trzeba teraz obsługiwać ręcznie lub przez property, jeśli potrzebne.


class DriverAbsence(Base):
    __tablename__ = 'driver_absences'
    id = Column(Integer, primary_key=True)
    driver_id = Column(Integer, ForeignKey('drivers.id', ondelete='CASCADE'), nullable=False)
    start_date = Column(Date, nullable=False)
    end_date = Column(Date, nullable=False)
    reason = Column(String(50), nullable=False)  # np. 'L4', 'UW', 'UO', 'Inne'
    comment = Column(String(255), nullable=True)
    firma_id = Column(Integer, ForeignKey('firma.id', ondelete="CASCADE"),  nullable=False)
    created_at = Column(DateTime, default=func.now())


class ClientNote(Base):
    __tablename__ = 'client_notes'

    id = Column(Integer, primary_key=True)
    client_id = Column(Integer, ForeignKey('clients.id', ondelete='CASCADE'), nullable=False)
    content = Column(Text, nullable=False)
    category = Column(String(50), default='general')
    created_by_name = Column(String(255))
    created_at = Column(DateTime(timezone=True), server_default=func.now())
    updated_at = Column(DateTime(timezone=True), onupdate=func.now())
    firma_id = Column(Integer, ForeignKey('firma.id', ondelete="CASCADE"),  nullable=False)
    # Relacja do klienta (opcjonalna, ale przydatna)
    client = relationship("Client", backref="notes")


class Driver(Base):
    __tablename__ = "drivers"
    id = Column(Integer, primary_key=True)
    full_name = Column(String(255), nullable=False, unique=True)
    active = Column(Boolean, default=True)
    phone = Column(String(50))
    firma_id = Column(Integer, ForeignKey('firma.id', ondelete="CASCADE"), nullable=False)


class ScheduleSlot(Base):
    __tablename__ = 'schedule_slots'
    id = Column(Integer, primary_key=True)
    group_id = Column(UUID(as_uuid=True), ForeignKey('event_groups.id', ondelete="CASCADE"))
    client_id = Column(Integer, ForeignKey('clients.id'))
    therapist_id = Column(Integer, ForeignKey('therapists.id'))
    driver_id = Column(Integer, ForeignKey('drivers.id'))
    kind = Column(Enum('therapy', 'pickup', 'dropoff', name='session_kind', create_type=False), nullable=False)
    starts_at = Column(DateTime(timezone=True))
    ends_at = Column(DateTime(timezone=True))
    status = Column(String, default='planned')
    distance_km = Column(Float)
    session_id = Column(UUID(as_uuid=True), nullable=True)
    run_id = Column(UUID(as_uuid=True), nullable=True)
    place_from = Column(String)
    place_to = Column(String)
    vehicle_id = Column(Integer)
    attendance = relationship("IndividualSessionAttendance", uselist=False, cascade="all, delete-orphan")
    group_tus_id = Column(Integer, ForeignKey('tus_groups.id'), nullable=True)
    firma_id = Column(Integer, ForeignKey('firma.id', ondelete="CASCADE"),  nullable=False)


class TUSGroupMember(Base):
    __tablename__ = "tus_group_members"
    group_id = Column(Integer, ForeignKey("tus_groups.id", ondelete="CASCADE"), primary_key=True)
    client_id = Column(Integer, ForeignKey("clients.id", ondelete="CASCADE"), primary_key=True)
    is_active = Column(Boolean, default=True, nullable=False)
    join_date = Column(Date, default=func.current_date())
    leave_date = Column(Date, nullable=True)
    firma_id = Column(Integer, ForeignKey('firma.id', ondelete="CASCADE"), nullable=False)
    client = relationship("Client", back_populates="group_associations")
    group = relationship("TUSGroup", back_populates="member_associations")


def _create_member_association(client):
    return TUSGroupMember(client=client)


# --- MODEL PLANU TUS ---
class TUSPlanItem(Base):
    __tablename__ = 'tus_plan_items'

    id = Column(Integer, primary_key=True)
    group_id = Column(Integer, ForeignKey('tus_groups.id'), nullable=False)
    semester = Column(Integer, default=1)  # 1 = zimowy, 2 = letni
    planned_date = Column(Date, nullable=False)
    topic = Column(String(255), nullable=False)
    is_executed = Column(Boolean, default=False)  # Czy zajęcia się odbyły?
    firma_id = Column(Integer, ForeignKey('firma.id', ondelete="CASCADE"),  nullable=False)
    # Relacja zwrotna
    group = relationship("TUSGroup", back_populates="plan_items")


class TUSGroup(Base):
    __tablename__ = "tus_groups"
    id = Column(Integer, primary_key=True)
    name = Column(String(255), nullable=False, unique=True)
    therapist_id = Column(Integer, ForeignKey("therapists.id", ondelete="SET NULL"))
    assistant_therapist_id = Column(Integer, ForeignKey("therapists.id", ondelete="SET NULL"))
    plan_items = relationship("TUSPlanItem", back_populates="group", cascade="all, delete-orphan")
    
    # --- POPRAWIONE RELACJE ---
    therapist = relationship("Therapist", back_populates="tus_groups", lazy="selectin", foreign_keys=[therapist_id])
    sessions = relationship("TUSSession", back_populates="group", cascade="all, delete-orphan", lazy="selectin")
    assistant_therapist = relationship("Therapist", lazy="selectin", foreign_keys=[assistant_therapist_id])
    # POPRAWKA: Definiujemy relację do obiektu pośredniczącego
    member_associations = relationship("TUSGroupMember", back_populates="group", cascade="all, delete-orphan")
    # "Proxy" sprawia, że group.members jest wygodną listą klientów
    # Association proxy z dodanym creatorem
    members = association_proxy(
        'member_associations',  # <-- ZMIANA Z 'group_members' NA 'member_associations'
        'client',
        creator=_create_member_association
    )

    # Dodatkowe pola na cele punktowe
    halfyear_target_points = Column(Integer)
    halfyear_reward = Column(String)
    annual_target_points = Column(Integer)
    annual_reward = Column(String)
    schedule_days = Column(ARRAY(Date))
    firma_id = Column(Integer, ForeignKey('firma.id', ondelete="CASCADE"),  nullable=False)


class TUSTopic(Base):
    __tablename__ = 'tus_topics'
    id = Column(Integer, primary_key=True)
    title = Column(String, nullable=False, unique=True)
    description = Column(String)
    firma_id = Column(Integer, ForeignKey('firma.id', ondelete="CASCADE"),  nullable=False)


class TUSSession(Base):
    __tablename__ = "tus_sessions"
    id = Column(Integer, primary_key=True)
    group_id = Column(Integer, ForeignKey("tus_groups.id", ondelete="CASCADE"), nullable=False)
    session_date = Column(Date, nullable=False)
    session_time = Column(Time)
    topic_id = Column(Integer, ForeignKey("tus_topics.id", ondelete="SET NULL"))
    bonuses_awarded = Column(Integer, default=0)
    group = relationship("TUSGroup", back_populates="sessions", lazy="joined")
    topic = relationship("TUSTopic")
    plan_item_id = Column(Integer, ForeignKey("tus_plan_items.id", ondelete="SET NULL"), nullable=True)

    scores = relationship("TUSSessionMemberScore", back_populates="session", cascade="all, delete-orphan")
    member_bonuses = relationship("TUSMemberBonus", back_populates="session", cascade="all, delete-orphan")
    attendance = relationship("TUSSessionAttendance", cascade="all, delete-orphan")
    firma_id = Column(Integer, ForeignKey('firma.id', ondelete="CASCADE"), nullable=False)
    # --- KONIEC ---


####

class TUSMemberBonus(Base):
    __tablename__ = 'tus_member_bonuses'
    id = Column(Integer, primary_key=True)
    session_id = Column(Integer, ForeignKey('tus_sessions.id', ondelete="CASCADE"), nullable=False)
    client_id = Column(Integer, ForeignKey('clients.id', ondelete="CASCADE"), nullable=False)
    points = Column(Integer, nullable=False, default=0)
    created_at = Column(DateTime, server_default=func.now())
    session = relationship("TUSSession", back_populates="member_bonuses")
    client = relationship("Client")
    firma_id = Column(Integer, ForeignKey('firma.id', ondelete="CASCADE"),  nullable=False)


class TUSBehavior(Base):
    __tablename__ = 'tus_behaviors'
    id = Column(Integer, primary_key=True)
    title = Column(String, unique=True, nullable=False)
    description = Column(String)
    default_max_points = Column(Integer, nullable=False, default=3)
    active = Column(Boolean, nullable=False, default=True)
    firma_id = Column(Integer, ForeignKey('firma.id', ondelete="CASCADE"), nullable=False)


class TUSGeneralBonus(Base):
    __tablename__ = 'tus_general_bonuses'
    id = Column(Integer, primary_key=True)
    group_id = Column(Integer, ForeignKey('tus_groups.id', ondelete="CASCADE"), nullable=False)
    client_id = Column(Integer, ForeignKey('clients.id', ondelete="CASCADE"), nullable=False)
    points = Column(Integer, default=0)
    reason = Column(String(255))
    created_at = Column(DateTime, default=datetime.utcnow)
    # Nowe pola
    semester = Column(Integer, default=1)
    reward_text = Column(String(255))
    firma_id = Column(Integer, ForeignKey('firma.id', ondelete="CASCADE"),  nullable=False)
    client = relationship("Client", lazy="joined")


class TUSSessionBehavior(Base):
    __tablename__ = 'tus_session_behaviors'
    id = Column(Integer, primary_key=True)
    session_id = Column(Integer, ForeignKey('tus_sessions.id', ondelete="CASCADE"), nullable=False)
    behavior_id = Column(Integer, ForeignKey('tus_behaviors.id'), nullable=False)
    max_points = Column(Integer, nullable=False, default=3)
    __table_args__ = (UniqueConstraint('session_id', 'behavior_id'),)
    firma_id = Column(Integer, ForeignKey('firma.id', ondelete="CASCADE"),  nullable=False)


class TUSSessionMemberScore(Base):
    __tablename__ = 'tus_session_member_scores'
    id = Column(Integer, primary_key=True)
    session_id = Column(Integer, ForeignKey('tus_sessions.id', ondelete="CASCADE"), nullable=False)
    client_id = Column(Integer, ForeignKey('clients.id', ondelete="CASCADE"), nullable=False)
    behavior_id = Column(Integer, ForeignKey('tus_behaviors.id'), nullable=False)
    points = Column(Integer, nullable=False, default=0)
    __table_args__ = (UniqueConstraint('session_id', 'client_id', 'behavior_id'),)
    session = relationship("TUSSession", back_populates="scores")
    firma_id = Column(Integer, ForeignKey('firma.id', ondelete="CASCADE"),  nullable=False)


class TUSSessionPartialReward(Base):
    __tablename__ = 'tus_session_partial_rewards'
    id = Column(Integer, primary_key=True)
    session_id = Column(Integer, ForeignKey('tus_sessions.id', ondelete="CASCADE"), nullable=False)
    client_id = Column(Integer, ForeignKey('clients.id', ondelete="CASCADE"), nullable=False)
    awarded = Column(Boolean, nullable=False, default=False)
    note = Column(String)
    awarded_at = Column(DateTime(timezone=True))
    __table_args__ = (UniqueConstraint('session_id', 'client_id'),)
    firma_id = Column(Integer, ForeignKey('firma.id', ondelete="CASCADE"),  nullable=False)


class TUSGroupTarget(Base):
    __tablename__ = 'tus_group_targets'
    id = Column(Integer, primary_key=True)
    group_id = Column(Integer, ForeignKey('tus_groups.id', ondelete="CASCADE"), nullable=False)
    school_year_start = Column(Integer, nullable=False)  # Np. 2025 dla roku 2025/2026
    semester = Column(Integer, nullable=False)  # 1 lub 2
    target_points = Column(Integer, nullable=False, default=0)
    reward = Column(String)
    firma_id = Column(Integer, ForeignKey('firma.id', ondelete="CASCADE"),  nullable=False)

    __table_args__ = (UniqueConstraint('group_id', 'school_year_start', 'semester'),)


class Project(Base):
    __tablename__ = 'projects'
    id = Column(Integer, primary_key=True)
    title = Column(String(255), nullable=False)
    description = Column(String)
    start_date = Column(Date)
    end_date = Column(Date)
    status = Column(String(50), default='planowany')  # planowany, w_trakcie, zakończony
    budget = Column(Float)
    coordinator = Column(String(255))
    partners = Column(String)  # Lista partnerów (tekst)
    beneficiaries_count = Column(Integer)
    photo_url = Column(String)
    created_at = Column(DateTime(timezone=True), server_default=func.now())
    updated_at = Column(DateTime(timezone=True), onupdate=func.now())
    firma_id = Column(Integer, ForeignKey('firma.id', ondelete="CASCADE"),  nullable=False)


class EventGroup(Base):
    __tablename__ = 'event_groups'
    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    client_id = Column(Integer, ForeignKey('clients.id'))
    label = Column(String)
    slots = relationship("ScheduleSlot", cascade="all, delete-orphan")
    firma_id = Column(Integer, ForeignKey('firma.id', ondelete="CASCADE"),  nullable=False)


class User(Base, UserMixin):  # Upewnij się, że masz UserMixin z flask_login
    __tablename__ = 'users'
    id = Column(Integer, primary_key=True)
    username = Column(String(80), unique=True, nullable=False)
    password_hash = Column(String(255), nullable=False)
    is_admin = Column(Boolean, default=False, nullable=False)
    is_secretariat = Column(Boolean, nullable=False, default=False)

    # === NOWE POLA DODANE ===
    full_name = Column(String(255), nullable=False, default='Imię Nazwisko')
    phone = Column(String(50), nullable=True)
    birth_date = Column(Date, nullable=True)
    firma_id = Column(Integer, ForeignKey('firma.id', ondelete="CASCADE"), nullable=False)

    # === NOWE POLE UPRAWNIEŃ (RBAC) ===
    # Przechowuje string np.: "clients,suo,planer"
    permissions = Column(String(500), default="")
    # ========================

    # === WIDOCZNE MODUŁY (wybrane przez użytkownika) ===
    # Przechowuje string np.: "dziennik,client_panel,poczekalnia".
    # Pusty string = domyślnie wszystkie moduły są widoczne (stare zachowanie).
    visible_modules = Column(String(500), default="")
    # ===================== ===

    therapist_id = Column(Integer, ForeignKey('therapists.id'), nullable=True)
    driver_id = Column(Integer, ForeignKey('drivers.id'), nullable=True)

    therapist_profile = relationship("Therapist", foreign_keys=[therapist_id])
    driver_profile = relationship("Driver", foreign_keys=[driver_id])

    def set_password(self, password):
        self.password_hash = generate_password_hash(password)

    def check_password(self, password):
        return check_password_hash(self.password_hash, password)

    # === METODA POMOCNICZA DO SPRAWDZANIA DOSTĘPU ===
    # W klasie User (app.py)

    def has_permission(self, module_name):
        """Sprawdza czy użytkownik ma dostęp do danego modułu."""
        # Admin ma dostęp do wszystkiego automatycznie
        if self.is_admin:
            return True

        # Jeśli brak uprawnień w bazie
        if not self.permissions:
            return False

        # === POPRAWKA: strip() usuwa spacje przy podziale ===
        perms = [p.strip() for p in self.permissions.split(',')]
        return module_name in perms

    # === MODUŁY WIDOCZNE W MENU (wybór użytkownika) ===

    def allowed_module_keys(self):
        """Klucze modułów, do których użytkownik MA prawo (admin: wszystkie)."""
        if self.is_admin:
            return [m['key'] for m in ALL_MODULES]
        perms = [p.strip() for p in (self.permissions or '').split(',') if p.strip()]
        result = []
        for m in ALL_MODULES:
            aliases = list(m.get('perms') or []) + [m['key']]
            # Moduły otwarte (tylko @login_required) są dostępne dla każdego zalogowanego
            if m['key'] in OPEN_MODULE_KEYS or any(a in perms for a in aliases):
                result.append(m['key'])
        return result

    def get_visible_modules(self):
        """
        Zwraca listę kluczy modułów, które mają być widoczne w menu.
        Brak wyboru (pusty string) = wszystkie moduły dozwolone dla użytkownika
        (admin: wszystkie) — domyślne, wstecznie kompatybilne zachowanie.
        """
        allowed = self.allowed_module_keys()
        if not self.visible_modules:
            return allowed
        chosen = [m.strip() for m in self.visible_modules.split(',') if m.strip()]
        if not chosen:
            return allowed
        keys = [m['key'] for m in ALL_MODULES]
        if self.is_admin:
            return [k for k in keys if k in chosen]
        allowed_set = set(allowed)
        return [k for k in keys if k in chosen and k in allowed_set]


@login_manager.user_loader
def load_user(user_id):
    session = SessionLocal()
    try:
        user = session.query(User).get(int(user_id))
        if user:
            # To jest kluczowe! Odłączamy obiekt od sesji,
            # żeby mógł być używany w HTML po zamknięciu tej funkcji.
            session.expunge(user)
        return user
    except Exception as e:
        print(f"Błąd load_user: {e}")
        return None
    finally:
        session.close()  # Zawsze zamykaj sesję!


# Zalecane: Zamykanie sesji po każdym żądaniu, żeby nie zapchać bazy
@app.teardown_appcontext
def shutdown_session(exception=None):
    SessionLocal.remove()


class SystemLog(Base):
    __tablename__ = 'system_logs'
    id = Column(Integer, primary_key=True)
    user_id = Column(Integer, nullable=True)
    username = Column(String(100), nullable=True)
    action = Column(String(255), nullable=False)
    details = Column(Text, nullable=True)
    ip_address = Column(String(50), nullable=True)
    created_at = Column(DateTime, default=func.now())
    firma_id = Column(Integer, ForeignKey('firma.id', ondelete="CASCADE"), nullable=True, default=1)


class AppSetting(Base):
    """Ustawienia aplikacji typu klucz-wartość (np. harmonogram automatycznych przypomnień)."""
    __tablename__ = 'app_settings'

    id = Column(Integer, primary_key=True)
    key = Column(String(100), unique=True, nullable=False)
    value = Column(Text, nullable=True)
    updated_at = Column(DateTime(timezone=True), server_default=func.now(), onupdate=func.now())


# === MODELE DZIENNIKA ===
class JournalEntry(Base):
    __tablename__ = 'dziennik'
    id = Column(Integer, primary_key=True)
    data = Column(Date, nullable=False)
    client_id = Column(Integer, ForeignKey('clients.id', ondelete="RESTRICT"), nullable=False)
    therapist_id = Column(Integer, ForeignKey('therapists.id', ondelete="RESTRICT"), nullable=False)
    temat = Column(String(255))
    cele = Column(TEXT)
    created_at = Column(DateTime(timezone=True), server_default=func.now())
    updated_at = Column(DateTime(timezone=True), onupdate=func.now())

    # Relacje ułatwiające pobieranie pełnych nazw
    client = relationship("Client", foreign_keys=[client_id], lazy="joined")
    therapist = relationship("Therapist", foreign_keys=[therapist_id], lazy="joined")
    firma_id = Column(Integer, ForeignKey('firma.id', ondelete="CASCADE"),  nullable=False)


class DiaryUser(Base):
    __tablename__ = 'diary_users'
    id = Column(Integer, primary_key=True)
    public_token = Column(String(36), unique=True, nullable=False)
    created_at = Column(DateTime, server_default=func.now())

    # Relacja do wpisów
    entries = relationship("DiaryEntry", backref="user", cascade="all, delete-orphan")
    firma_id = Column(Integer, ForeignKey('firma.id', ondelete="CASCADE"), nullable=False)


class DiaryEntry(Base):
    __tablename__ = 'diary_entries'
    id = Column(Integer, primary_key=True)
    diary_user_id = Column(Integer, ForeignKey('diary_users.id'), nullable=False)
    data = Column(Date, nullable=False)
    temat = Column(String(255))
    cele = Column(TEXT)
    created_at = Column(DateTime, server_default=func.now())
    firma_id = Column(Integer, ForeignKey('firma.id', ondelete="CASCADE"), nullable=False)


# === WCZYTANIE MODELI AI ===
CT_MODEL_PATH = "models/ct_recommender.pkl"
CD_MODEL_PATH = "models/cd_recommender.pkl"

ct_model, cd_model = None, None
try:
    if os.path.exists(CT_MODEL_PATH):
        ct_model = joblib.load(CT_MODEL_PATH)
        print("Model rekomendacji terapeutów wczytany.")
except Exception as e:
    print(f"BŁĄD: Nie można wczytać modelu terapeutów: {e}")

try:
    if os.path.exists(CD_MODEL_PATH):
        cd_model = joblib.load(CD_MODEL_PATH)
        print("Model rekomendacji kierowców wczytany.")
except Exception as e:
    print(f"BŁĄD: Nie można wczytać modelu kierowców: {e}")


# === FUNKCJE POMOCNICZE ===
@contextmanager
def session_scope():
    """Ujednolicony context manager dla sesji ORM."""
    session = SessionLocal()
    try:
        yield session
        # Zmieniono z db_session.commit() na session.commit()
        session.commit()
    except Exception as e:
        session.rollback()
        # Ważne: wydrukuj błąd, aby zobaczyć, co się stało przed rollbackiem
        print(f"BŁĄD W TRANSAKCJI (ROLLBACK): {e}")
        raise
    finally:
        session.close()




    # if pierwszy_terapeuta:
    # print(f"Znaleziono terapeutę: {pierwszy_terapeuta.full_name}")


def init_finance_records_table():
    with engine.begin() as conn:
        conn.execute(text('''
            CREATE TABLE IF NOT EXISTS paid_records (
                id SERIAL PRIMARY KEY,
                client_id INTEGER NOT NULL REFERENCES clients(id) ON DELETE CASCADE,
                service_id INTEGER REFERENCES paid_services(id),
                amount FLOAT NOT NULL,
                payment_date DATE NOT NULL,
                description TEXT,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            )
        '''))
        conn.execute(text("CREATE INDEX IF NOT EXISTS idx_paid_records_date ON paid_records(payment_date)"))
    print("✓ Tabela paid_records zainicjalizowana")


def get_main_clinic_address():
    """
    Pobiera adres główny poradni z tabeli 'firma'.
    Zwraca string np.: 'ul. Prosta 10, 00-001 Warszawa'
    """
    try:
        with engine.connect() as conn:
            # Pobieramy pierwszy rekord z tabeli firma
            # (Zakładamy, że jest tylko jedna firma/fundacja w systemie)
            row = conn.execute(text("""
                SELECT ulica, numer_budynku, kod_pocztowy, miasto 
                FROM firma 
                LIMIT 1
            """)).mappings().first()

            if row:
                # Budujemy adres dla Google Maps
                # Format: Ulica Numer, Kod Miasto
                adres = f"{row['ulica']} {row['numer_budynku']}, {row['kod_pocztowy']} {row['miasto']}"
                return adres

    except Exception as e:
        print(f"Błąd pobierania adresu firmy: {e}")

    # FALLBACK (Zabezpieczenie):
    # Jeśli tabela jest pusta, wpisz tu swój prawdziwy adres "na sztywno"
    return "Warszawa, Polska"


# === ULEPSZONY SYSTEM LOGOWANIA ===

def log_activity(action, details=None, level="INFO"):
    """
    Zapisuje zdarzenie w bazie danych ORAZ wypisuje je w konsoli (dla monitoringu na żywo).
    Używa niezależnej sesji, aby nie zamykać ani nie zakłócać transakcji wywołującej.
    """
    user_id = None
    username = "System/Tło"
    ip_address = "127.0.0.1"
    firma_id = 1

    if has_request_context():
        user_id = session.get('user_id')
        username = session.get('username', 'Niezalogowany')
        firma_id = session.get('firma_id', 1)

        if request.headers.getlist("X-Forwarded-For"):
            ip_address = request.headers.getlist("X-Forwarded-For")[0]
        else:
            ip_address = request.remote_addr

    timestamp = datetime.now().strftime('%Y-%m-%d %H:%M:%S')
    log_msg = f"[{level}] {timestamp} | USER: {username} | ACTION: {action} | DETAILS: {details} | IP: {ip_address}"

    if level == "ERROR":
        logging.error(log_msg)
    elif level == "WARNING":
        logging.warning(log_msg)
    else:
        logging.info(log_msg)

    try:
        # Tworzymy niezależną instancję sesji, by nie naruszać scoped_session głównej transakcji
        db = SessionLocal.session_factory()
        try:
            new_log = SystemLog(
                user_id=user_id,
                username=username,
                action=str(action)[:255],
                details=str(details) if details else None,
                ip_address=ip_address,
                firma_id=firma_id
            )
            db.add(new_log)
            db.commit()
        except Exception as db_e:
            db.rollback()
            logging.error(f"Nie udało się zapisać logu do bazy: {db_e}")
        finally:
            db.close()
    except Exception as e:
        logging.error(f"!!! CRITICAL: Błąd w log_activity: {e}")


def get_route_distance(origin, destination):
    """Oblicza dystans między dwoma punktami za pomocą Google Maps API."""
    print(f"\n{'=' * 60}")
    print(f"FUNKCJA get_route_distance() WYWOŁANA")
    print(f"Origin: '{origin}'")
    print(f"Destination: '{destination}'")

    api_key = GOOGLE_MAPS_API_KEY
    print(f"Klucz API w funkcji: {api_key[:20]}..." if api_key else "❌ BRAK")

    if not api_key:
        print("⚠️ OSTRZEŻENIE: Brak klucza GOOGLE_MAPS_API_KEY. Obliczanie dystansu nie zadziała.")
        return None

    if not origin or not destination:
        print("⚠️ OSTRZEŻENIE: Brak origin lub destination")
        return None

    origin_safe = requests.utils.quote(origin)
    destination_safe = requests.utils.quote(destination)
    url = f"https://maps.googleapis.com/maps/api/directions/json?origin={origin_safe}&destination={destination_safe}&key={api_key}"

    print(f"📡 URL (bez klucza): ...{url[-50:]}")

    try:
        print("📤 Wysyłam zapytanie do Google Maps...")
        response = requests.get(url, timeout=10)  # Zwiększony timeout
        print(f"📥 Status code: {response.status_code}")

        response.raise_for_status()
        data = response.json()

        print(f"📊 Status API: {data.get('status')}")

        if data.get('status') == 'OK':
            distance_meters = data['routes'][0]['legs'][0]['distance']['value']
            distance_km = round(distance_meters / 1000, 2)
            print(f"✅ SUKCES! Dystans: {distance_km} km")
            print(f"{'=' * 60}\n")
            return distance_km
        else:
            print(f"❌ Błąd API: {data.get('status')}")
            print(f"   Komunikat: {data.get('error_message', 'Brak')}")
            print(f"   Pełna odpowiedź: {data}")
            print(f"{'=' * 60}\n")
            return None

    except requests.exceptions.Timeout:
        print(f"⏱️ TIMEOUT: Zapytanie przekroczyło limit czasu")
        print(f"{'=' * 60}\n")
        return None
    except requests.exceptions.RequestException as e:
        print(f"❌ Błąd połączenia z Google Maps API: {e}")
        print(f"{'=' * 60}\n")
        return None
    except (KeyError, IndexError) as e:
        print(f"❌ Błąd parsowania odpowiedzi: {e}")
        print(f"   Struktura danych: {data}")
        print(f"{'=' * 60}\n")
        return None
    except Exception as e:
        print(f"❌ Nieoczekiwany błąd: {type(e).__name__}: {e}")
        import traceback
        print(traceback.format_exc())
        print(f"{'=' * 60}\n")
        return None


def _time_bucket(hhmm: str) -> str:
    """Zaokrągla czas do najbliższych 30 minut w dół (np. 09:10 -> 09:00)."""
    h, m = map(int, hhmm.split(":"))
    m = 0 if m < 30 else 30
    return f"{h:02d}:{m:02d}"


def _date_str(dt):
    """Konwertuje obiekt daty na string w formacie YYYY-MM-DD."""
    return dt.strftime("%Y-%m-%d")


def _score(freq, maxfreq, recency_days):
    """Oblicza wynik na podstawie częstości i świeżości interakcji."""
    if maxfreq <= 0:
        base = 0.0
    else:
        base = (freq + 1.0) / (maxfreq + 2.0)
    rec_bonus = 0.3 * exp(-recency_days / 30.0) if recency_days is not None else 0.0
    return min(1.0, base + rec_bonus)


def _parse_time(s: str):
    """Parsuje string HH:MM na krotkę (godzina, minuta)."""
    h, m = map(int, s.split(":"))
    return h, m


def _to_tstz(date_yyyy_mm_dd: str, hhmm: str, tz=TZ):
    """Tworzy obiekt datetime ze strefą czasową na podstawie daty i czasu."""
    h, m = _parse_time(hhmm)
    d = datetime.fromisoformat(date_yyyy_mm_dd)
    return d.replace(hour=h, minute=m, second=0, microsecond=0, tzinfo=tz)


def _availability_conflicts(conn, therapist_id=None, driver_id=None, starts_at=None, ends_at=None):
    """Sprawdza konflikty w harmonogramie dla danej osoby i czasu."""
    return find_overlaps(conn,
                         therapist_id=therapist_id,
                         driver_id=driver_id,
                         starts_at=starts_at, ends_at=ends_at)




def _score_cd_row(r):
    """Heurystyka oceny dopasowania klient-kierowca (fallback dla AI)."""
    n = r.get("n_runs", 0) or 0
    mins = r.get("minutes_sum", 0) or 0
    done = r.get("done_ratio", 0.0) or 0.0
    rec = r.get("recency_weight", 0.0) or 0.0
    return 0.5 * rec + 0.3 * done + 0.2 * min(1.0, n / 10.0) + 0.1 * min(1.0, mins / 600.0)


# Poprawiona funkcja find_overlaps z wykluczeniem aktualnie edytowanego slotu
# Poprawiona funkcja find_overlaps (pozwala na stykające się terminy)
def find_overlaps(conn, therapist_id, starts_at, ends_at, exclude_slot_id=None, firma_id=None, **kwargs):
    """
    Sprawdza, czy w podanym terminie terapeuta ma już inne zajęcia.
    exclude_slot_id: ID wizyty, którą właśnie edytujemy (żeby nie kolidowała sama ze sobą).
    Pozwala na stykające się terminy (np. koniec 12:00, start 12:00).
    Zabezpieczona parametrem firma_id dla izolacji danych placówek (Multi-tenant).
    """
    query = """
        SELECT 
            ss.id, 
            ss.starts_at, 
            ss.ends_at, 
            c.full_name as client_name,
            ss.kind
        FROM schedule_slots ss
        LEFT JOIN clients c ON ss.client_id = c.id
        WHERE ss.therapist_id = :tid 
          AND ss.status != 'cancelled'
          -- NOWA LOGIKA: Zajęcia kolidują tylko wtedy, gdy się zazębiają.
          -- Znak = został usunięty, by pozwolić na "styk" (np. end = start).
          AND ss.starts_at < :end 
          AND ss.ends_at > :start
    """

    params = {
        "tid": therapist_id,
        "start": starts_at,
        "end": ends_at
    }

    if exclude_slot_id:
        query += " AND ss.id != :exc_id"
        params["exc_id"] = exclude_slot_id

    # Izolacja danych w ramach wybranej firmy (SaaS)
    if firma_id:
        query += " AND ss.firma_id = :firma_id"
        params["firma_id"] = firma_id

    return conn.execute(text(query), params).mappings().all()


def ensure_shared_run_id_for_driver(conn, driver_id, starts_at, ends_at):
    """Znajduje lub tworzy wspólne ID dla kursów odbywających się w tym samym czasie."""
    q = text("""
          SELECT id, run_id FROM schedule_slots
          WHERE driver_id = :did AND starts_at = :s AND ends_at = :e
          LIMIT 1
        """)
    row = conn.execute(q, {"did": driver_id, "s": starts_at, "e": ends_at}).mappings().first()
    if not row:
        return None

    if row["run_id"] is None:
        new_run = str(uuid.uuid4())
        conn.execute(
            text("UPDATE schedule_slots SET run_id = :rid WHERE id = :id"),
            {"rid": new_run, "id": row["id"]}
        )
        return new_run
    return row["run_id"]


def ensure_shared_session_id_for_therapist(conn, therapist_id, starts_at, ends_at):
    """Znajduje lub tworzy wspólne ID dla sesji terapeutycznych w tym samym czasie."""
    q = text("""
          SELECT id, session_id FROM schedule_slots
          WHERE therapist_id = :tid AND starts_at = :s AND ends_at = :e
          LIMIT 1
        """)
    row = conn.execute(q, {"tid": therapist_id, "s": starts_at, "e": ends_at}).mappings().first()
    if not row:
        return None
    if row["session_id"] is None:
        new_sid = str(uuid.uuid4())
        conn.execute(
            text("UPDATE schedule_slots SET session_id = :sid WHERE id = :id"),
            {"sid": new_sid, "id": row["id"]}
        )
        return new_sid
    return row["session_id"]


@app.route('/api/available-therapists', methods=['GET'])
def get_available_therapists():
    current_firma_id = session.get('firma_id', 1) # Pobranie tenantu
    try:
        with engine.begin() as conn:
            therapists = conn.execute(text("""
                SELECT id, full_name, specialization
                FROM therapists 
                WHERE active = true AND firma_id = :firma_id
                ORDER BY full_name
            """), {"firma_id": current_firma_id}).mappings().all()
            return jsonify([dict(t) for t in therapists]), 200
    except Exception as e:
        return jsonify({"error": str(e)}), 500


# Endpoint do sprawdzania dostępności terapeuty
# W pliku app.py

@app.route('/api/check-availability', methods=['POST'])
def check_availability():
    """Sprawdza dostępność terapeuty w danym czasie i zwraca szczegóły kolizji."""

    # 1. Pobierz dane
    data = request.get_json(silent=True) or {}
    therapist_id = data.get('therapist_id')
    starts_at_str = data.get('starts_at')
    ends_at_str = data.get('ends_at')
    exclude_slot_id = data.get('exclude_slot_id')

    if not all([therapist_id, starts_at_str, ends_at_str]):
        return jsonify({"error": "Brak wymaganych pól"}), 400

    try:
        # 2. Przetwórz daty (UTC -> TZ)
        s_dt = datetime.fromisoformat(starts_at_str.replace('Z', '+00:00')).astimezone(TZ)
        e_dt = datetime.fromisoformat(ends_at_str.replace('Z', '+00:00')).astimezone(TZ)

        with engine.connect() as conn:
            # 3. Znajdź kolizje
            # Funkcja find_overlaps (którą masz zdefiniowaną wcześniej) zwraca listę słowników
            conflicts = find_overlaps(conn, therapist_id=therapist_id,
                                      starts_at=s_dt, ends_at=e_dt,
                                      exclude_slot_id=exclude_slot_id)

            # 4. Sformatuj wynik dla frontendu
            conflict_details = []
            for c in conflicts:
                # Formatuj datę dla czytelności
                start_fmt = c['starts_at'].astimezone(TZ).strftime('%H:%M')
                end_fmt = c['ends_at'].astimezone(TZ).strftime('%H:%M')

                conflict_details.append({
                    "id": c['id'],
                    "client_name": c.get('client_name', 'Nieznany klient'),
                    "time": f"{start_fmt}-{end_fmt}",
                    "kind": c.get('kind', 'therapy'),
                    "schedule_type": c.get('schedule_type', 'individual')
                })

            return jsonify({
                "available": len(conflicts) == 0,
                "conflicts": conflict_details
            }), 200

    except Exception as e:
        print(f"Błąd sprawdzania dostępności: {e}")
        import traceback
        traceback.print_exc()
        return jsonify({"error": str(e)}), 500

def check_availability_in_range(availability, start_date, end_date):
    """Sprawdza czy klient ma dostępność w wybranym zakresie dat"""
    from datetime import datetime, timedelta
    
    start = datetime.strptime(start_date, '%Y-%m-%d')
    end = datetime.strptime(end_date, '%Y-%m-%d')
    
    # Dla każdego dnia w zakresie
    current = start
    while current <= end:
        day_of_week = current.isoweekday()  # 1-7 (Pon-Ndz)
        
        # Sprawdź czy ten dzień jest dostępny
        for slot in availability:
            if slot['day_of_week'] == day_of_week:
                return True
        
        current += timedelta(days=1)
    
    return False


@app.route('/api/clients/<int:client_id>/generate-plan', methods=['POST'])
@login_required
def generate_therapeutic_plan(client_id):
    """
    Generuje plan terapeutyczny na podstawie diagnozy (RODO Compliant).
    """
    try:
        with session_scope() as session:
            client = session.query(Client).get(client_id)
            if not client:
                return jsonify({'error': 'Klient nie istnieje'}), 404

            if not client.diagnosis:
                return jsonify({'error': 'Brak diagnozy w systemie. Najpierw wgraj lub wpisz diagnozę.'}), 400

            # 1. PRZYGOTOWANIE DANYCH ANONIMOWYCH
            # Określenie formy (Pacjent/Pacjentka) na podstawie imienia (zakładamy format "Nazwisko Imię")
            # W języku polskim imiona żeńskie kończą się zazwyczaj na 'a'
            parts = client.full_name.split()
            first_name = parts[1] if len(parts) > 1 else parts[0]
            pseudo_name = "Pacjentka" if first_name.endswith('a') else "Pacjent"

            # Wiek zamiast daty urodzenia
            age_info = f"wiek: {client.age} lat" if client.age else "wiek nieznany"

            # 2. CZYSZCZENIE TREŚCI DIAGNOZY (USUNIĘCIE DANYCH OSOBOWYCH)
            # Zamieniamy imię i nazwisko w tekście diagnozy na pseudonim
            safe_diagnosis = client.diagnosis.replace(client.full_name, pseudo_name)

            # Dodatkowe czyszczenie poszczególnych członów nazwiska (dla bezpieczeństwa)
            for part in parts:
                if len(part) > 2:  # Pomijamy bardzo krótkie słowa
                    safe_diagnosis = safe_diagnosis.replace(part, pseudo_name)

            # --- AI GENERATION ---
            api_key = os.getenv("GOOGLE_AI_API_KEY")
            if not api_key:
                return jsonify({'error': 'Brak klucza API Google.'}), 500

            import google.generativeai as genai
            genai.configure(api_key=api_key)
            model = genai.GenerativeModel('gemini-3.5-flash')

            # 3. BEZPIECZNY PROMPT
            prompt = f"""
            Jesteś doświadczonym terapeutą prowadzącym i koordynatorem planów leczenia.
            Twoim zadaniem jest przygotowanie profesjonalnego Planu Terapeutycznego dla osoby: {pseudo_name}, {age_info}.

            ZANONIMIZOWANE DANE MEDYCZNE (Diagnoza/Zalecenia):
            "{safe_diagnosis}"

            ZADANIE:
            Stwórz ustrukturyzowany plan w formacie HTML (użyj znaczników <h3>, <ul>, <li>, <p>, <strong>), 
            który będzie zawierał następujące sekcje:
            1. Cele Długoterminowe (Główne kierunki pracy)
            2. Cele Krótkoterminowe (Na najbliższe 3-6 miesięcy)
            3. Proponowane Metody i Formy Terapii (np. TUS, terapia indywidualna, SI - dobierz adekwatnie do problemów opisanych w diagnozie)
            4. Zalecenia do pracy w domu
            5. Wskazówki dla nauczycieli/szkoły (jeśli dotyczy dziecka)

            WAŻNE: 
            - Nie używaj żadnych imion ani nazwisk. Stosuj formę "{pseudo_name}".
            - Styl: Merytoryczny, empatyczny, konkretny. 
            - Nie dodawaj wstępu typu "Oto plan", po prostu zwróć treść HTML.
            """

            response = model.generate_content(prompt)
            generated_plan = response.text.strip()

            # Usuwamy ewentualne znaczniki markdown
            generated_plan = generated_plan.replace('```html', '').replace('```', '')

            return jsonify({'plan': generated_plan})

    except Exception as e:
        print(f"Błąd generowania planu: {e}")
        return jsonify({'error': str(e)}), 500


@app.route('/api/clients/<int:client_id>/plan', methods=['GET', 'POST'])
@login_required
def handle_client_plan(client_id):
    """Pobiera (GET) lub Zapisuje (POST) plan terapeutyczny."""
    try:
        with session_scope() as session:
            client = session.query(Client).get(client_id)
            if not client: return jsonify({'error': 'Klient nie istnieje'}), 404

            if request.method == 'GET':
                return jsonify({
                    'id': client.id,
                    'full_name': client.full_name,
                    'diagnosis': client.diagnosis,
                    'therapeutic_plan': client.therapeutic_plan
                })

            if request.method == 'POST':
                data = request.get_json()
                new_plan = data.get('plan')
                client.therapeutic_plan = new_plan
                return jsonify({'message': 'Plan zapisany pomyślnie.'})

    except Exception as e:
        return jsonify({'error': str(e)}), 500


# --- NOWY ENDPOINT DLA PRZYDZIAŁU (ALOKACJI SUO) ---
@app.route('/api/suo/allocation', methods=['POST'])
@app.route('/api/suo/allocation/<int:client_id>/<string:month_key>', methods=['PUT'])
@login_required
def handle_suo_allocation(client_id=None, month_key=None):
    """
    Zapisuje lub aktualizuje przydział godzin SUO dla danego klienta i miesiąca.
    Rozwiązuje błąd 409 poprzez wyszukiwanie wyłącznie po kluczu unikalnym.
    """
    data = request.get_json(silent=True) or {}

    raw_client_id = client_id or data.get('client_id')
    try:
        final_client_id = int(raw_client_id)
    except (ValueError, TypeError):
        return jsonify({"error": "Nieprawidłowy lub brakujący identyfikator klienta."}), 400

    final_month_key = month_key or data.get('month_key')
    if not final_month_key:
        return jsonify({"error": "Określenie miesiąca (month_key) jest wymagane."}), 400

    raw_minutes_quota = data.get('minutes_quota')
    try:
        minutes_quota_hours = float(raw_minutes_quota)
    except (ValueError, TypeError):
        return jsonify({"error": "Przydział godzin musi być prawidłową liczbą."}), 400

    if minutes_quota_hours < 0:
        return jsonify({"error": "Przydział godzin nie może być ujemny."}), 400

    # Przeliczamy godziny podane z formularza na minuty do bazy danych
    final_minutes_quota = int(minutes_quota_hours * 60)
    current_firma_id = session.get('firma_id', 1)

    try:
        with session_scope() as db_session:
            # RODO Check: Czy pacjent należy do firmy zalogowanego managera
            client_verification = db_session.query(Client).filter_by(id=final_client_id, firma_id=current_firma_id).first()
            if not client_verification:
                return jsonify({"error": "Odmowa dostępu. Brak uprawnień do tego pacjenta."}), 403

            # FIX 409: Szukamy stricte po kryteriach Unique Constraint bazy danych!
            allocation = db_session.query(SuoAllocation).filter_by(
                client_id=final_client_id,
                month_key=final_month_key
            ).first()

            if allocation:
                # Aktualizacja istniejącego rekordu (oraz naprawa/migracja firma_id)
                allocation.minutes_quota = final_minutes_quota
                allocation.firma_id = current_firma_id
                action = "updated"
            else:
                # Tworzenie nowego wpisu
                allocation = SuoAllocation(
                    client_id=final_client_id,
                    month_key=final_month_key,
                    minutes_quota=final_minutes_quota,
                    firma_id=current_firma_id
                )
                db_session.add(allocation)
                action = "created"

            db_session.flush()

        return jsonify({
            "success": True,
            "message": f"Przydział godzin został zapisany ({action}).",
            "client_id": final_client_id,
            "month_key": final_month_key
        }), 200

    except IntegrityError as e:
        print(f"❌ SUO Alocation Error: {e}")
        return jsonify({"error": "Konflikt zapisu limitu w bazie danych."}), 409
    except Exception as e:
        print(f"❌ Krytyczny błąd SUO: {e}")
        return jsonify({"error": str(e)}), 500


# --- CENNIK (Zarządzanie usługami) ---
@app.route('/api/paid-services', methods=['GET', 'POST'])
@login_required
def handle_paid_services():
    if request.method == 'GET':
        with session_scope() as session:
            services = session.query(PaidService).filter_by(active=True).all()
            return jsonify([{'id': s.id, 'name': s.name, 'price': s.price} for s in services])

    if request.method == 'POST':
        data = request.get_json()
        with session_scope() as session:
            new_service = PaidService(name=data['name'], price=float(data['price']))
            session.add(new_service)
        return jsonify({'success': True}), 201


# --- 1. DODAWANIE WPŁATY ---
@app.route('/api/finance/records', methods=['POST'])
@admin_required
def add_paid_record():
    data = request.get_json()
    try:
        with session_scope() as session:
            # Pobieramy cenę z usługi, jeśli nie podano ręcznie
            amount = float(data.get('amount', 0))
            if amount == 0 and data.get('service_id'):
                service = session.query(PaidService).get(data['service_id'])
                if service: amount = service.price

            new_record = PaidRecord(
                client_id=data['client_id'],
                service_id=data.get('service_id'),
                payment_date=datetime.strptime(data['payment_date'], '%Y-%m-%d').date(),
                amount=amount,
                description=data.get('description', '')
            )
            session.add(new_record)
        return jsonify({'message': 'Zapisano wpłatę'}), 201
    except Exception as e:
        return jsonify({'error': str(e)}), 500


# --- 2. LISTA WPŁAT (Filtrowanie po roku) ---
@app.route('/api/finance/records', methods=['GET'])
@login_required
def get_paid_records():
    year = request.args.get('year', type=int)
    client_id = request.args.get('client_id', type=int)
    current_firma_id = session.get('firma_id', 1)

    with session_scope() as session_db:
        query = session_db.query(PaidRecord).options(joinedload(PaidRecord.client), joinedload(PaidRecord.service)).filter(PaidRecord.firma_id == current_firma_id)
        if year:
            query = query.filter(extract('year', PaidRecord.payment_date) == year)
        if client_id:
            query = query.filter(PaidRecord.client_id == client_id)

        records = query.order_by(PaidRecord.payment_date.desc()).all()
        return jsonify([{
            'id': r.id, 'client_name': r.client.full_name if r.client else 'Nieznany',
            'service_name': r.service.name if r.service else 'Inne', 'amount': r.amount,
            'date': r.payment_date.isoformat(), 'description': r.description
        } for r in records])


# --- 3. USUWANIE WPŁATY ---
@app.route('/api/finance/records/<int:rid>', methods=['DELETE'])
@admin_required
def delete_paid_record(rid):
    with session_scope() as session:
        session.query(PaidRecord).filter_by(id=rid).delete()
    return jsonify({'success': True}), 200


# --- 4. SUMA ROCZNA DLA SPRAWOZDANIA (To pobiera sprawozdania.html) ---
@app.route('/api/finance/summary', methods=['GET'])
@login_required
def get_finance_year_summary():
    year = request.args.get('year', type=int)
    if not year: return jsonify({'total': 0})
    current_firma_id = session.get('firma_id', 1)

    with session_scope() as session_db:
        total = session_db.query(func.sum(PaidRecord.amount))\
            .filter(extract('year', PaidRecord.payment_date) == year, PaidRecord.firma_id == current_firma_id).scalar()
    return jsonify({'total': total if total else 0})


# --- RAPORT FINANSOWY (Zestawienie odpłatnych) ---
@app.route('/api/reports/paid-activity', methods=['GET'])
@admin_required
def get_paid_report():
    with session_scope() as session:
        # Pobieramy tylko klientów oznaczonych jako płatni
        clients = session.query(Client).options(joinedload(Client.paid_service)) \
            .filter(Client.is_paid == True, Client.active == True).all()

        report = []
        total_sum = 0.0

        for c in clients:
            service_name = c.paid_service.name if c.paid_service else "Nie przypisano usługi"
            price = c.paid_service.price if c.paid_service else 0.0

            report.append({
                'client_id': c.id,
                'full_name': c.full_name,
                'service': service_name,
                'price': price
            })
            total_sum += price

        return jsonify({
            'rows': report,
            'total_sum': total_sum,
            'count': len(report)
        })


# === DEKORATORY I HOOKI FLASK ===
@app.before_request
def parse_json_only_when_needed():
    if request.method in ('POST', 'PUT', 'PATCH'):
        g.json = request.get_json(silent=True) or {}
    else:
        g.json = None


# === GŁÓWNE ENDPOINTY APLIKACJI ===

# @app.get("/")
# def index():
#    return app.send_static_file("index.html")


@app.get("/api/ai/gaps")
def ai_gaps():
    """
        ?month=YYYY-MM
        Zwraca listy:
          - clients_without_therapy_days: [ {client_id, full_name, date}, ... ]
          - therapists_idle_days: [ {therapist_id, full_name, date}, ... ]
          - drivers_idle_days: [ {driver_id, full_name, date}, ... ]
        """
    mk = request.args.get("month") or datetime.now(TZ).strftime("%Y-%m")
    first = datetime.fromisoformat(mk + "-01").date()
    # prosty zakres – do końca miesiąca
    if first.month == 12:
        nxt = first.replace(year=first.year + 1, month=1, day=1)
    else:
        nxt = first.replace(month=first.month + 1, day=1)
    days = []
    d = first
    while d < nxt:
        days.append(d)
        d += timedelta(days=1)

    with engine.begin() as conn:
        # Klienci aktywni
        current_firma_id = session.get('firma_id', 1)
        clients = conn.execute(text("SELECT id, full_name FROM clients WHERE active=true AND firma_id = :fid"), {"fid": current_firma_id}).mappings().all()
        therapists = conn.execute(text("SELECT id, full_name FROM therapists WHERE active=true")).mappings().all()
        drivers = conn.execute(text("SELECT id, full_name FROM drivers WHERE active=true")).mappings().all()

        # sloty w miesiącu
        q = text("""
              SELECT kind, client_id, therapist_id, driver_id,
                     (starts_at AT TIME ZONE 'Europe/Warsaw')::date AS d
              FROM schedule_slots
              WHERE to_char(starts_at AT TIME ZONE 'Europe/Warsaw','YYYY-MM') = :mk
            """)
        rows = conn.execute(q, {"mk": mk}).mappings().all()

    # indeksy
    had_therapy = {(r["client_id"], r["d"]) for r in rows if r["kind"] == "therapy"}
    th_worked = {(r["therapist_id"], r["d"]) for r in rows if r["therapist_id"] and r["kind"] == 'therapy'}
    dr_worked = {(r["driver_id"], r["d"]) for r in rows if r["driver_id"] and r["kind"] in ('pickup', 'dropoff')}

    clients_without = []
    for c in clients:
        for d in days:
            if (c["id"], d) not in had_therapy:
                clients_without.append({"id": c["id"], "full_name": c["full_name"], "date": _date_str(d)})

    therapists_idle = []
    for t in therapists:
        for d in days:
            if (t["id"], d) not in th_worked:
                therapists_idle.append({"id": t["id"], "full_name": t["full_name"], "date": _date_str(d)})

    drivers_idle = []
    for dr in drivers:
        for d in days:
            if (dr["id"], d) not in dr_worked:
                drivers_idle.append({"id": dr["id"], "full_name": dr["full_name"], "date": _date_str(d)})

    return jsonify({
        "clients_without_therapy_days": clients_without,
        "therapists_idle_days": therapists_idle,
        "drivers_idle_days": drivers_idle
    }), 200


@app.post("/api/ai/suggest")
def ai_suggest():
    """
        JSON:
        {
          "client_id": 123,
          "date": "2025-08-22",          # dzień planowania
          "therapy_window": ["08:00","16:00"],   # opcjonalnie
          "pickup_offset_min": 30,       # ile przed terapią
          "dropoff_offset_min": 30       # ile po terapii
        }

        Zwraca: Sugerowanych terapeutów/kierowców wraz z obliczonym score (wynikiem dopasowania)
        i zaproponowanymi godzinami slotów.
    """
    data = request.get_json(silent=True) or {}

    # 1. Weryfikacja Client ID
    try:
        cid = int(data["client_id"])
    except (KeyError, ValueError, TypeError):
        # To się zdarzy, jeśli frontend wyśle null/brak ID klienta
        print("DIAGNOZA: Błąd parsowania client_id w ai_suggest.")
        return jsonify({"error": "client_id jest wymagany i musi być liczbą"}), 400

    date_str = data.get("date", date.today().isoformat())
    window = data.get("therapy_window") or ["08:00", "16:00"]
    pk_off = int(data.get("pickup_offset_min", 30))
    dp_off = int(data.get("dropoff_offset_min", 30))

    # Wprowadzenie tych zmiennych jest wymagane dla kodu, mimo że są domyślne w JS
    try:
        sh, sm = _parse_time(window[0])
        eh, em = _parse_time(window[1])
    except:
        return jsonify({"error": "Nieprawidłowy format okna czasowego (therapy_window)"}), 400

    start_bucket = _time_bucket(window[0])
    end_bucket = _time_bucket(window[1])

    all_buckets = []
    cur_h, cur_m = sh, sm
    while (cur_h, cur_m) <= (eh, em):
        all_buckets.append(f"{cur_h:02d}:{cur_m:02d}")
        if cur_m == 0:
            cur_h, cur_m = cur_h, 30
        else:
            cur_h, cur_m = cur_h + 1, 0

    with engine.begin() as conn:
        # --- BLOK 1: TERAPEUCI (Z WBUDOWANYM FALLBACKIEM) ---

        # 1a. Zapytanie z LEFT JOIN (pobiera aktywnych terapeutów z historią, nawet jeśli historia jest pusta)
        q1 = text("""
                SELECT t.id, t.full_name, COALESCE(v.n, 0) AS n, v.last_dt
                FROM therapists t
                LEFT JOIN v_hist_client_therapist v
                  ON v.therapist_id = t.id AND v.client_id = :cid
                WHERE t.active = true
            """)
        th_rows = [dict(r) for r in conn.execute(q1, {"cid": cid}).mappings().all()]

        if not th_rows:
            # Powinno się zdarzyć tylko, jeśli w ogóle nie ma aktywnych terapeutów.
            print("DIAGNOZA: Brak aktywnych terapeutów.")
            return jsonify({"therapy": [], "drivers_pickup": [], "drivers_dropoff": []}), 200

        # 1b. Normalizacja i liczenie kandydatów
        max_n_th = max((r["n"] for r in th_rows), default=0)

        # 1c. Preferencje godzinowe (niezmienione)
        q_thh = text("""
              SELECT therapist_id, hhmm, n FROM v_hist_therapist_hour
              WHERE hhmm = ANY(:buckets)
            """)
        thh = conn.execute(q_thh, {"buckets": all_buckets}).mappings().all()
        pref_map = {}
        for r in thh:
            pref_map.setdefault(r["therapist_id"], {})[r["hhmm"]] = r["n"]

        therapy_candidates = []
        today = datetime.now(TZ).date()

        # 1d. Iteracja po terapeutach i sprawdzanie kolizji
        for r in th_rows:
            last_dt = r["last_dt"]
            rec_days = (today - last_dt.date()).days if last_dt else None
            base_score = _score(r["n"], max_n_th, rec_days)

            hours_pref = pref_map.get(r["id"], {})
            best_bucket = max(all_buckets, key=lambda b: hours_pref.get(b, 0)) if all_buckets else window[
                0]  # Użyj window[0] jako domyślnego

            th_start = _to_tstz(date_str, best_bucket)
            th_end = th_start + timedelta(minutes=60)

            # Sprawdzenie kolizji i przesunięcie (niezmienione)
            col = _availability_conflicts(conn, therapist_id=r["id"], starts_at=th_start, ends_at=th_end)
            if col:
                tried = set([best_bucket])
                ok = False
                for b in all_buckets:
                    if b in tried: continue
                    s2 = _to_tstz(date_str, b);
                    e2 = s2 + timedelta(minutes=60)
                    if not _availability_conflicts(conn, therapist_id=r["id"], starts_at=s2, ends_at=e2):
                        best_bucket, th_start, th_end = b, s2, e2
                        ok = True
                        break
                if not ok:
                    continue  # Pomijamy niedostępnych

            therapy_candidates.append({
                "therapist_id": r["id"],
                "full_name": r["full_name"],
                "score": round(base_score, 3),
                "suggested_start": th_start.isoformat(),
                "suggested_end": th_end.isoformat()
            })

        therapy_candidates.sort(key=lambda x: x["score"], reverse=True)
        therapy_candidates = therapy_candidates[:5]

        # --- BLOK 2: KIEROWCY (Z WBUDOWANYM FALLBACKIEM) ---
        drivers_pickup = []
        drivers_dropoff = []

        if therapy_candidates:
            best_th = therapy_candidates[0]
            th_s = datetime.fromisoformat(best_th["suggested_start"])
            th_e = datetime.fromisoformat(best_th["suggested_end"])

            pk_end = th_s
            pk_start = pk_end - timedelta(minutes=pk_off)

            dp_start = th_e
            dp_end = dp_start + timedelta(minutes=dp_off)

            # 2a. Zapytanie z LEFT JOIN dla kierowców
            q2 = text("""
                    SELECT d.id, d.full_name, COALESCE(v.n,0) AS n, v.last_dt
                    FROM drivers d
                    LEFT JOIN v_hist_client_driver v
                      ON v.driver_id = d.id AND v.client_id = :cid
                    WHERE d.active = true
                """)
            dr_rows = [dict(r) for r in conn.execute(q2, {"cid": cid}).mappings().all()]
            max_n_dr = max((r["n"] for r in dr_rows), default=0)

            # 2b. Preferencje godzinowe kierowców (niezmienione)
            buckets_needed = list({_time_bucket(pk_start.strftime("%H:%M")),
                                   _time_bucket(dp_start.strftime("%H:%M"))})
            q_drh = text("""
                  SELECT driver_id, hhmm, n FROM v_hist_driver_hour
                  WHERE hhmm = ANY(:buckets)
                """)
            drh = conn.execute(q_drh, {"buckets": buckets_needed}).mappings().all()
            dr_pref = {}
            for r in drh:
                dr_pref.setdefault(r["driver_id"], {})[r["hhmm"]] = r["n"]

            # 2c. Iteracja po kierowcach
            for r in dr_rows:
                # Pickup
                rec_days = (today - r["last_dt"].date()).days if r["last_dt"] else None
                base = _score(r["n"], max_n_dr, rec_days)
                bpk = _time_bucket(pk_start.strftime("%H:%M"))
                base_pk = base + (0.05 if dr_pref.get(r["id"], {}).get(bpk, 0) > 0 else 0.0)

                col = _availability_conflicts(conn, driver_id=r["id"], starts_at=pk_start, ends_at=pk_end)
                if not col:
                    drivers_pickup.append({
                        "driver_id": r["id"], "full_name": r["full_name"],
                        "score": round(base_pk, 3),
                        "suggested_start": pk_start.isoformat(),
                        "suggested_end": pk_end.isoformat()
                    })

                # Dropoff
                bdp = _time_bucket(dp_start.strftime("%H:%M"))
                base_dp = base + (0.05 if dr_pref.get(r["id"], {}).get(bdp, 0) > 0 else 0.0)
                col2 = _availability_conflicts(conn, driver_id=r["id"], starts_at=dp_start, ends_at=dp_end)
                if not col2:
                    drivers_dropoff.append({
                        "driver_id": r["id"], "full_name": r["full_name"],
                        "score": round(base_dp, 3),
                        "suggested_start": dp_start.isoformat(),
                        "suggested_end": dp_end.isoformat()
                    })

            drivers_pickup.sort(key=lambda x: x["score"], reverse=True)
            drivers_dropoff.sort(key=lambda x: x["score"], reverse=True)
            drivers_pickup = drivers_pickup[:5]
            drivers_dropoff = drivers_dropoff[:5]

    return jsonify({
        "therapy": therapy_candidates,
        "drivers_pickup": drivers_pickup,
        "drivers_dropoff": drivers_dropoff
    }), 200


def _softmax(x):
    m = max(x) if x else 0.0
    exps = [math.exp(v - m) for v in x]
    s = sum(exps) or 1.0
    return [v / s for v in exps]


def _score_ct_row(r):
    # prosta, działająca od ręki heurystyka
    # wagi możesz potem zgrać z modelem ML
    n = r.get("n_sessions", 0) or 0
    mins = r.get("minutes_sum", 0) or 0
    done = r.get("done_ratio", 0.0) or 0.0
    rec = r.get("recency_weight", 0.0) or 0.0
    return 0.5 * rec + 0.3 * done + 0.2 * min(1.0, n / 10.0) + 0.1 * min(1.0, mins / 600.0)


@app.route('/api/clients/simple-list', methods=['GET'])
@login_required
def get_clients_simple_list():
    """Zwraca uproszczoną listę słownikową z blokadą podmiotu."""
    current_firma_id = session.get('firma_id', 1)
    try:
        with session_scope() as db_session:
            # POPRAWKA: Dodano .filter_by(firma_id=current_firma_id)
            clients = db_session.query(Client).filter_by(active=True, firma_id=current_firma_id).order_by(Client.full_name).all()
            return jsonify([{'id': c.id, 'text': c.full_name} for c in clients]), 200
    except Exception as e:
        return jsonify({'error': str(e)}), 500


@app.get("/api/ai/recommend")
def ai_recommend():
    """
        Zwraca TOP propozycje terapeuty i kierowcy dla klienta + preferowane godziny.
        Używa wytrenowanych modeli AI, jeśli są dostępne.
        """
    cid = request.args.get("client_id", type=int)
    if not cid:
        return jsonify({"error": "client_id is required"}), 400

    with engine.begin() as conn:
        # TERAPEUCI
        q_ct = text("""
              SELECT f.therapist_id, t.full_name,
                     f.n_sessions, f.minutes_sum, f.done_ratio, f.days_since_last, f.recency_weight
              FROM v_ct_features f
              JOIN therapists t ON t.id=f.therapist_id AND t.active=true
              WHERE f.client_id=:cid
            """)
        ct_rows = [dict(r) for r in conn.execute(q_ct, {"cid": cid}).mappings().all()]

        # KIEROWCY
        q_cd = text("""
              SELECT f.driver_id, d.full_name,
                     f.n_runs, f.minutes_sum, f.done_ratio, f.days_since_last, f.recency_weight
              FROM v_cd_features f
              JOIN drivers d ON d.id=f.driver_id AND d.active=true
              WHERE f.client_id=:cid
            """)
        cd_rows = [dict(r) for r in conn.execute(q_cd, {"cid": cid}).mappings().all()]

        # Preferencje czasu (bez zmian)
        qtp = text("SELECT dow, hour, cnt FROM v_client_time_prefs WHERE client_id=:cid ORDER BY cnt DESC LIMIT 6")
        time_prefs = [dict(r) for r in conn.execute(qtp, {"cid": cid}).mappings().all()]

    # Użyj modelu AI do oceny terapeutów, jeśli jest wczytany
    if ct_model and ct_rows:
        features = ["n_sessions", "minutes_sum", "done_ratio", "days_since_last", "recency_weight"]
        X_ct = pd.DataFrame(ct_rows)[features]
        # predict_proba zwraca prawdopodobieństwo dla klasy "1" (dobre dopasowanie)
        scores = ct_model.predict_proba(X_ct)[:, 1]
        for r, score in zip(ct_rows, scores):
            r["score"] = round(score, 4)
    else:  # Fallback do starej logiki, jeśli model nie jest dostępny
        for r in ct_rows:
            r["score"] = round(_score_ct_row(r), 4)

    # Użyj modelu AI do oceny kierowców, jeśli jest wczytany
    if cd_model and cd_rows:
        features = ["n_runs", "minutes_sum", "done_ratio", "days_since_last", "recency_weight"]
        X_cd = pd.DataFrame(cd_rows)[features]
        scores = cd_model.predict_proba(X_cd)[:, 1]
        for r, score in zip(cd_rows, scores):
            r["score"] = round(score, 4)
    else:  # Fallback
        for r in cd_rows:
            r["score"] = round(_score_cd_row(r), 4)

    # Sortuj wyniki i zwróć TOP 5
    ct_rows.sort(key=lambda x: x["score"], reverse=True)
    cd_rows.sort(key=lambda x: x["score"], reverse=True)

    return jsonify({
        "therapists": ct_rows[:5],
        "drivers": cd_rows[:5],
        "time_prefs": time_prefs
    }), 200


@app.route('/api/auth/me')
@login_required  # Wymaga, aby użytkownik był zalogowany
def get_current_user_permissions():
    """
    Zwraca uprawnienia i dane aktualnie zalogowanego użytkownika.
    Zwraca canEditClientData (Admin LUB Terapeuta LUB Sekretariat) dla frontendu.
    """
    try:
        # Pobieranie podstawowych flag
        is_admin = session.get('is_admin', False)
        # Używamy is not None, aby upewnić się, że to jest flaga boolowska, a nie ID
        is_therapist_profile = session.get('therapist_id') is not None
        is_secretariat = session.get('is_secretariat', False)
        driver_id = session.get('driver_id')
        username = session.get('username', 'Nieznany')
        therapist_id = session.get('therapist_id')

        # 1. Obliczenie flagi uprawniającej do edycji klientów:
        # Dostęp ma: Admin LUB Terapeuta LUB Sekretariat
        can_edit_client_data = is_admin or is_therapist_profile or is_secretariat

        # 2. Budowanie obiektu uprawnień
        permissions = {
            'username': username,
            'isAuthenticated': True,

            # --- Role bazowe ---
            'isAdmin': is_admin,
            'isSecretariat': is_secretariat,
            'isDriver': driver_id is not None,
            'isTherapist': is_therapist_profile,

            # --- Flaga dostępu do edycji (spełnia Pan wymóg) ---
            'canEditClientData': can_edit_client_data,
            'canDeleteClients': is_admin or current_user.has_permission('delete_clients'),

            # --- ID profili (jeśli są) ---
            'therapistId': therapist_id,
            'driverId': driver_id,

            # --- Widoczne moduły wybrane przez użytkownika (pozostałe ukryte w menu) ---
            'visibleModules': current_user.get_visible_modules(),
            'allModules': ALL_MODULES
        }

        # 3. Zwrócenie poprawnego obiektu JSON
        return jsonify(permissions), 200

    except Exception as e:
        # W przypadku błędu serwera (np. problem z sesją/bazą)
        print(f"Błąd krytyczny w /api/auth/me: {str(e)}")
        import traceback
        traceback.print_exc()
        return jsonify({'error': 'Nie można pobrać danych sesji użytkownika', 'details': str(e)}), 500

    except Exception as e:
        print(f"Błąd krytyczny w /api/auth/me: {str(e)}")
        import traceback
        traceback.print_exc()
        return jsonify({'error': 'Nie można pobrać danych sesji użytkownika', 'details': str(e)}), 500


@app.route('/api/admin/users/<int:user_id>/toggle-secretariat', methods=['POST'])
@admin_required  # Twój dekorator @admin_required już sprawdza, czy użytkownik jest adminem
def toggle_secretariat(user_id):
    """
    API Endpoint do przełączania roli 'Sekretariat' dla użytkownika.
    Używa Twojego context managera 'session_scope'.
    """

    # Pobierz ID admina wykonującego operację (z Twojej sesji)
    admin_user_id = session.get('user_id')

    try:
        with session_scope() as db_session:
            # 1. Pobierz admina (aby upewnić się, że na pewno istnieje)
            # Twój dekorator @admin_required już to zrobił, ale dla bezpieczeństwa
            admin_user = db_session.get(User, admin_user_id)
            if not admin_user or not admin_user.is_admin:
                return jsonify({"error": "Brak uprawnień (ponowna weryfikacja nieudana)"}), 403

            # 2. Pobierz użytkownika, którego rolę chcesz zmienić
            # Używamy db_session.get() zamiast User.query.get_or_404()
            user_to_toggle = db_session.get(User, user_id)

            if not user_to_toggle:
                return jsonify({"error": "Użytkownik nie znaleziony"}), 404

            # 3. Opcjonalne zabezpieczenie: Nie pozwól adminowi na zmianę roli samemu sobie
            # (Odkomentuj, jeśli potrzebne)
            # if user_to_toggle.id == admin_user_id:
            #    return jsonify({"error": "Nie możesz zmienić tej roli dla siebie"}), 400

            # 4. Przełącz wartość boolean
            user_to_toggle.is_secretariat = not user_to_toggle.is_secretariat

            # 5. Zapisz nowy status do sesji, jeśli użytkownik zmienia swoją własną rolę
            # (To rzadki przypadek, ale warto o tym pamiętać)
            if user_to_toggle.id == admin_user_id:
                session['is_secretariat'] = user_to_toggle.is_secretariat

            # 6. session_scope() automatycznie wykona db_session.commit()

            print(
                f"Admin '{admin_user.username}' zmienił status 'is_secretariat' dla '{user_to_toggle.username}' na: {user_to_toggle.is_secretariat}")

            # 7. Zwróć nowy status do JavaScriptu
            return jsonify({"is_secretariat": user_to_toggle.is_secretariat})

    except Exception as e:
        # session_scope() automatycznie wykona rollback w razie błędu
        print(f"Błąd krytyczny w toggle_secretariat: {str(e)}")
        import traceback
        traceback.print_exc()
        return jsonify({"error": f"Wewnętrzny błąd serwera: {str(e)}"}), 500


@app.route('/api/public/journal/<client_uuid>', methods=['GET', 'POST'])
def public_journal_api(client_uuid):
    """API obsługujące nową tabelę diary_entries."""

    try:
        with session_scope() as db_session:
            # 1. Weryfikacja tokenu w tabeli DiaryUser
            user = db_session.query(DiaryUser).filter_by(public_token=client_uuid).first()

            if not user:
                return jsonify({'error': 'Nieprawidłowy token.'}), 404

            # --- GET: POBIERANIE WPISÓW ---
            if request.method == 'GET':
                entries = db_session.query(DiaryEntry) \
                    .filter_by(diary_user_id=user.id) \
                    .order_by(DiaryEntry.data.desc(), DiaryEntry.created_at.desc()).all()

                results = []
                for entry in entries:
                    results.append({
                        'id': entry.id,
                        'data': entry.data.strftime('%Y-%m-%d'),
                        'temat': entry.temat,
                        'cele': entry.cele,
                        'terapeuta': 'Ty',  # Tutaj zawsze pisze użytkownik
                        'is_mine': True
                    })

                return jsonify(results)

            # --- POST: DODAWANIE WPISU ---
            if request.method == 'POST':
                data = request.get_json()

                if not data.get('data') or not data.get('temat'):
                    return jsonify({'error': 'Brak wymaganych danych.'}), 400

                # Tworzymy wpis w nowej tabeli DiaryEntry
                # Tutaj NIE MA pola therapist_id, więc błąd zniknie!
                new_entry = DiaryEntry(
                    diary_user_id=user.id,
                    data=datetime.strptime(data['data'], '%Y-%m-%d').date(),
                    temat=data['temat'],
                    cele=data.get('cele', '')
                )

                db_session.add(new_entry)
                db_session.commit()

                return jsonify({'message': 'Zapisano!', 'id': new_entry.id}), 201

    except Exception as e:
        print(f"Błąd API Dziennika: {e}")
        return jsonify({'error': str(e)}), 500


@app.route('/api/clients/<int:client_id>/get-link', methods=['POST'])
@login_required  # Zmieniono na login_required dla szerszego dostępu
def get_client_public_link(client_id):
    print(f"--- START: Generowanie linku dla klienta ID: {client_id} ---")
    try:
        with session_scope() as db_session:
            # 1. Pobieramy klienta
            client = db_session.query(Client).get(client_id)

            if not client:
                print(f"❌ BŁĄD: Klient o ID {client_id} nie istnieje w bazie.")
                return jsonify({'error': 'Klient nie istnieje'}), 404

            # 2. Generowanie tokenu
            if not client.public_token:
                import uuid
                token = str(uuid.uuid4())
                client.public_token = token
                # Wymuszamy zapis, aby baza na pewno to dostała
                db_session.flush()
                print(f"✅ Wygenerowano nowy token: {token}")
            else:
                print(f"ℹ️ Klient ma już token: {client.public_token}")

            # 3. Tworzenie linku
            # 'external_journal' to nazwa funkcji widoku, którą też masz w kodzie
            full_link = url_for('external_journal', client_uuid=client.public_token, _external=True)

            print(f"✅ SUKCES. Link: {full_link}")
            return jsonify({'link': full_link, 'message': 'Link wygenerowany'})

    except Exception as e:
        print(f"❌ BŁĄD KRYTYCZNY (500) podczas generowania linku: {str(e)}")
        # Wypisujemy dokładny błąd do logów, żebyś wiedział czy to brak kolumny czy coś innego
        import traceback
        traceback.print_exc()
        return jsonify({'error': f"Błąd serwera: {str(e)}"}), 500


@app.route('/api/admin/users/<int:user_id>/toggle-admin', methods=['POST'])
@admin_required  # Użyj swojego dekoratora do sprawdzania uprawnień admina
def toggle_admin_role(user_id):
    """
    API Endpoint do przełączania roli 'Admin' dla użytkownika.
    """

    # Pobierz ID admina wykonującego operację (z Twojej sesji)
    admin_user_id = session.get('user_id')

    # === WAŻNE ZABEZPIECZENIE ===
    # Nie pozwól nikomu (nawet adminowi) odebrać sobie uprawnień
    # Używamy operatora ==, ale bezpieczniej jest konwertować na ten sam typ
    if int(user_id) == int(admin_user_id):
        return jsonify({"error": "Nie możesz zmienić własnych uprawnień administratora"}), 403

    try:
        with session_scope() as db_session:
            # Pobierz użytkownika, którego rolę chcesz zmienić
            user_to_toggle = db_session.get(User, user_id)

            if not user_to_toggle:
                return jsonify({"error": "Użytkownik nie znaleziony"}), 404

            # Przełącz wartość boolean
            user_to_toggle.is_admin = not user_to_toggle.is_admin

            # session_scope() automatycznie wykona db_session.commit()

            admin_username = session.get('username', 'Admin')  # Pobierz nazwę admina do logów
            print(
                f"Admin '{admin_username}' zmienił status 'is_admin' dla '{user_to_toggle.username}' na: {user_to_toggle.is_admin}")

            # Zwróć nowy status do JavaScriptu
            return jsonify({"is_admin": user_to_toggle.is_admin})

    except Exception as e:
        # session_scope() automatycznie wykona rollback w razie błędu
        print(f"Błąd krytyczny w toggle_admin_role: {str(e)}")
        import traceback
        traceback.print_exc()
        return jsonify({"error": f"Wewnętrzny błąd serwera: {str(e)}"}), 500


@app.get("/api/clients")
@login_required
def list_clients_with_suo():
    """
    Zwraca listę klientów z wyliczonym saldem SUO.
    Wersja pancerna: zabezpieczona przed błędem 502 i odporna na brak kolumny photo_url.
    """
    try:
        mk = request.args.get("month") or datetime.now(TZ).strftime("%Y-%m")
        q = (request.args.get("q") or "").strip()
        therapist_id = request.args.get("therapist_id", type=int)
        include_inactive = request.args.get("include_inactive") in ("1", "true", "yes")

        # 1. Pobieramy ID firmy z aktywnej sesji (Tenant Lock)
        current_firma_id = session.get('firma_id', 1)

        # 2. Definiujemy warunki filtrowania Multi-tenant
        where = ["c.firma_id = :firma_id"]
        params = {"mk": mk, "firma_id": current_firma_id}

        if not include_inactive:
            where.append("c.active IS TRUE")
        if q:
            where.append("c.full_name ILIKE :q")
            params["q"] = f"%{q}%"
        if therapist_id:
            where.append("""
                    EXISTS (
                      SELECT 1 FROM schedule_slots s
                      WHERE s.client_id = c.id AND s.therapist_id = :tid AND s.kind = 'therapy'
                        AND to_char(s.starts_at AT TIME ZONE 'Europe/Warsaw','YYYY-MM') = :mk
                        AND s.firma_id = :firma_id
                    )
                """)
            params["tid"] = therapist_id

        where_sql = "WHERE " + " AND ".join(where) if where else ""

        # 3. Bezpieczne zapytanie SQL (photo_url zastąpione bezpiecznym NULL, jeśli kolumna nie istnieje)
        sql = f"""
            WITH used AS (
              SELECT 
                client_id, 
                COALESCE(SUM(EXTRACT(EPOCH FROM (ends_at - starts_at)) / 60), 0)::FLOAT AS minutes_used
              FROM schedule_slots
              WHERE to_char(starts_at AT TIME ZONE 'Europe/Warsaw','YYYY-MM') = :mk
                AND kind = 'therapy'
                AND status NOT IN ('planned', 'cancelled')
                AND firma_id = :firma_id
              GROUP BY client_id
            )
            SELECT
              c.id AS client_id, c.full_name, c.phone, c.address, c.active,
              NULL AS photo_url,  -- Zabezpieczenie przed brakiem kolumny w starej strukturze DB
               c.photo_consent,
              EXISTS (SELECT 1 FROM client_unavailability cu WHERE cu.client_id = c.id AND cu.firma_id = :firma_id) AS has_unavailability_plan,
              :mk AS month_key, 

              -- Przydział przeliczony na godziny
              COALESCE(a.minutes_quota::FLOAT / 60, 0) AS minutes_quota,

              -- Wykorzystano
              COALESCE(u.minutes_used, 0) AS minutes_used, 

              -- Obliczenie Pozostało
              CASE WHEN a.minutes_quota IS NULL THEN NULL
                   ELSE (a.minutes_quota - COALESCE(u.minutes_used, 0))
              END AS minutes_left,

              (a.minutes_quota IS NULL) AS needs_allocation
            FROM clients c
            LEFT JOIN used u ON u.client_id = c.id
            LEFT JOIN suo_allocations a ON a.client_id = c.id AND a.month_key = :mk AND a.firma_id = :firma_id
            {where_sql} 
            ORDER BY c.full_name;
            """
            
        with engine.begin() as conn:
            rows = conn.execute(text(sql), params).mappings().all()
            return jsonify([dict(r) for r in rows]), 200

    except Exception as e:
        # Jeśli cokolwiek wybuchnie, serwer nie rzuci błędem 502, tylko wypisze błąd w konsoli Rendera
        print(f"❌ KRYTYCZNY BŁĄD w /api/clients: {e}")
        import traceback
        traceback.print_exc() # Wyświetli dokładną linię błędu w logach serwera
        
        # Zwracamy czysty kod 500 z opisem błędu, by ułatwić debugowanie
        return jsonify({"error": "Wewnętrzny błąd bazy danych", "details": str(e)}), 500


@app.delete("/api/clients/<int:cid>")
@login_required
def delete_client(cid):
    """Trwale usuwa klienta i wszystkie jego powiązania (kaskadowo)."""

    # --- 1. ZABEZPIECZENIE (To musisz dodać) ---
    # Pozwalamy, jeśli user jest ADMINEM lub ma uprawnienie 'delete_clients'
    can_delete = current_user.is_admin or current_user.has_permission('delete_clients')

    if not can_delete:
        return jsonify({"error": "Brak uprawnień. Wymagany Admin lub uprawnienie do usuwania."}), 403
    # -------------------------------------------

    try:
        with engine.begin() as conn:
            # Opcjonalnie: Jeśli baza nie ma CASCADE, najpierw usuń powiązania ręcznie
            # np. conn.execute(text("DELETE FROM schedule_slots WHERE client_id=:id"), {"id": cid})

            # Właściwe usuwanie
            res = conn.execute(text("DELETE FROM clients WHERE id=:id"), {"id": cid})
            log_activity("USUNIECIE_KLIENTA", f"Admin usunął klienta ID: {cid}")

        if res.rowcount == 0:
            return jsonify({"error": "Nie znaleziono klienta"}), 404

        return "", 204

    except Exception as e:
        # Obsługa błędu, np. gdy klient ma przypisane wizyty, a baza blokuje usuwanie
        print(f"Błąd usuwania klienta {cid}: {e}")
        return jsonify({"error": "Nie można usunąć klienta (prawdopodobnie posiada powiązane dane, np. wizyty)."}), 500


@app.post("/api/clients")
@login_required
def create_client():
    # 1. Sprawdzenie uprawnień
    is_therapist = current_user.therapist_id is not None
    can_add = current_user.is_admin or current_user.has_permission('add_clients') or is_therapist
    if not can_add:
        return jsonify({"error": "Brak uprawnień do dodawania nowych klientów."}), 403

    # 2. Pobranie danych
    data = request.get_json(silent=True) or {}
    full_name = (data.get("full_name") or "").strip()
    short_name = (data.get("short_name") or "").strip() or None

    if not full_name:
        return jsonify({"error": "Pole 'full_name' jest wymagane."}), 400

    # --- ODRAZU POBIERAMY ID FIRMY Z SESJI UŻYTKOWNIKA ---
    current_firma_id = session.get('firma_id', 1)

    # 3. Dodajemy kolumnę firma_id do zapytania INSERT
    sql = """
        INSERT INTO clients (full_name, phone, address, active, short_name, photo_consent, firma_id)
        VALUES (:full_name, :phone, :address, :active, :short_name, :photo_consent, :firma_id)
        RETURNING id, full_name, phone, address, active, short_name, photo_consent, firma_id;
        """
    
    try:
        with engine.begin() as conn:
            row = conn.execute(text(sql), {
                "full_name": full_name,
                "phone": (data.get("phone") or None),
                "address": (data.get("address") or None),
                "active": bool(data.get("active", True)),
                "short_name": short_name,
                "photo_consent": data.get('photo_consent', True),  # <--- DODAJ!
                "firma_id": current_firma_id
            }).mappings().first()

            return jsonify(dict(row)), 201

    except IntegrityError as e:
        if hasattr(e.orig, "pgcode") and e.orig.pgcode == psycopg2.errorcodes.UNIQUE_VIOLATION:
            return jsonify({"error": "Taki klient już istnieje (imię i nazwisko)."}), 409
        return jsonify({"error": "Błąd integralności bazy.", "details": str(e.orig)}), 409
    except Exception as e:
        return jsonify({"error": f"Błąd serwera: {str(e)}"}), 500


@app.put("/api/clients/<int:cid>")
@login_required
def update_client(cid):
    data = request.get_json(silent=True) or {}

    full_name = (data.get("full_name") or "").strip()
    new_address = (data.get("address") or "").strip()

    try:
        with engine.begin() as conn:
            # 1. Pobierz stary adres (do logiki transportu)
            old_res = conn.execute(text("SELECT address FROM clients WHERE id=:id"), {"id": cid}).mappings().first()
            old_address = old_res['address'] if old_res else ""

            # 2. Update Profilu Klienta
            conn.execute(text("""
                UPDATE clients 
                SET full_name=:fn, phone=:ph, address=:addr, active=:act, 
                    photo_url=:p, diagnosis=:d, notes=:n,
                    photo_consent=:photo_consent
                WHERE id=:id
            """), {
                "id": cid, "fn": full_name, "ph": data.get("phone"),
                "addr": new_address, "act": data.get("active", True),
                "p": data.get("photo_url"), "d": data.get("diagnosis"), "n": data.get("notes"),
                "photo_consent": data.get('photo_consent', True)
            })

            alerts = ["Dane zapisane."]

            # Obsługa finansów (jeśli są w request)
            if 'is_paid' in data:
                is_paid_val = data['is_paid']
                conn.execute(text("UPDATE clients SET is_paid=:ip WHERE id=:id"), {"ip": is_paid_val, "id": cid})

            if 'paid_service_id' in data:
                pid = data['paid_service_id']
                pid_val = int(pid) if pid else None
                conn.execute(text("UPDATE clients SET paid_service_id=:pid WHERE id=:id"), {"pid": pid_val, "id": cid})

            # 3. AKTUALIZACJA TRAS (Jeśli adres się zmienił)
            if new_address and new_address != old_address:
                print(f"🔄 Zmiana adresu: '{old_address}' -> '{new_address}'")

                # Pobieramy przyszłe sloty
                slots = conn.execute(text("""
                    SELECT id, kind, place_from, place_to 
                    FROM schedule_slots
                    WHERE client_id=:cid AND kind IN ('pickup','dropoff') 
                    AND status='planned' AND starts_at > NOW()
                """), {"cid": cid}).mappings().all()

                count_ok = 0

                for slot in slots:
                    sid = slot['id']
                    origin = slot['place_from']
                    destination = slot['place_to']

                    if slot['kind'] == 'pickup':
                        origin = new_address
                    elif slot['kind'] == 'dropoff':
                        destination = new_address

                    # --- POPRAWKA TUTAJ ---
                    # Wcześniej było: dist, err = get_route_distance(...) -> TO POWODOWAŁO BŁĄD
                    # Teraz odbieramy pojedynczą wartość (float lub None)
                    dist = get_route_distance(origin, destination)

                    if dist is not None:
                        count_ok += 1
                        final_dist = dist
                    else:
                        final_dist = 0
                    # -----------------------

                    conn.execute(text("""
                        UPDATE schedule_slots 
                        SET place_from = :orig, 
                            place_to = :dest, 
                            distance_km = :dist
                        WHERE id = :sid
                    """), {
                        "orig": origin,
                        "dest": destination,
                        "dist": final_dist,
                        "sid": sid
                    })

                if count_ok > 0:
                    alerts.append(f"Zaktualizowano miejscowość i dystans w {count_ok} kursach.")

            # LOGOWANIE ZMIAN
            try:
                log_activity("EDYCJA_KLIENTA", f"Zaktualizowano dane klienta: {full_name} (ID: {cid})")
            except:
                pass

            return jsonify({"status": "success", "message": " ".join(alerts)}), 200

    except IntegrityError as e:
        # Sprawdzamy czy to błąd unikalności (duplikat)
        if hasattr(e.orig, "pgcode") and e.orig.pgcode == psycopg2.errorcodes.UNIQUE_VIOLATION:
            return jsonify({"error": f"Klient o nazwisku '{full_name}' już istnieje w bazie."}), 409

        print(f"Błąd bazy przy edycji klienta: {e}")
        return jsonify({"error": "Błąd integralności danych."}), 500

    except Exception as e:
        import traceback
        traceback.print_exc()
        return jsonify({"error": str(e)}), 500


@app.route('/api/groups/<group_id>', methods=['GET'])
def get_package_group(group_id):
    """Pobiera pakiet na podstawie UUID group_id"""
    conn = None
    cur = None

    try:
        conn = psycopg2.connect(
            host='localhost',
            port='5432',
            database='suo',  # ZMIEŃ
            user='postgres',  # ZMIEŃ
            password='EDUQ'  # ZMIEŃ
        )
        cur = conn.cursor(cursor_factory=RealDictCursor)

        # Pobierz wszystkie sloty należące do grupy (UUID)
        cur.execute("""
                SELECT 
                    id as slot_id,
                    group_id::text as group_id,
                    client_id,
                    kind,
                    therapist_id,
                    driver_id,
                    vehicle_id,
                    starts_at,
                    ends_at,
                    place_from,
                    place_to,
                    status,
                    distance_km
                FROM schedule_slots
                WHERE group_id = %s::uuid
                ORDER BY 
                    CASE kind 
                        WHEN 'pickup' THEN 1
                        WHEN 'therapy' THEN 2
                        WHEN 'dropoff' THEN 3
                        ELSE 4
                    END
            """, (group_id,))

        slots = cur.fetchall()

        if not slots:
            return jsonify({"error": "Pakiet nie znaleziony"}), 404

        # Podstawowe info z pierwszego slotu
        first = slots[0]
        result = {
            "group_id": first["group_id"],
            "client_id": first["client_id"],
            "status": first["status"],
            "label": None  # Możesz dodać label jeśli masz w bazie
        }

        # Rozdziel sloty według typu
        for slot in slots:
            if slot["kind"] == "therapy":
                result["therapy"] = {
                    "slot_id": slot["slot_id"],
                    "therapist_id": slot["therapist_id"],
                    "starts_at": slot["starts_at"].isoformat() if slot["starts_at"] else None,
                    "ends_at": slot["ends_at"].isoformat() if slot["ends_at"] else None,
                    "place": slot["place_to"],
                    "status": slot["status"]
                }
            elif slot["kind"] == "pickup":
                result["pickup"] = {
                    "slot_id": slot["slot_id"],
                    "driver_id": slot["driver_id"],
                    "vehicle_id": slot["vehicle_id"],
                    "starts_at": slot["starts_at"].isoformat() if slot["starts_at"] else None,
                    "ends_at": slot["ends_at"].isoformat() if slot["ends_at"] else None,
                    "from": slot["place_from"],
                    "to": slot["place_to"],
                    "status": slot["status"]
                }
            elif slot["kind"] == "dropoff":
                result["dropoff"] = {
                    "slot_id": slot["slot_id"],
                    "driver_id": slot["driver_id"],
                    "vehicle_id": slot["vehicle_id"],
                    "starts_at": slot["starts_at"].isoformat() if slot["starts_at"] else None,
                    "ends_at": slot["ends_at"].isoformat() if slot["ends_at"] else None,
                    "from": slot["place_from"],
                    "to": slot["place_to"],
                    "status": slot["status"]
                }

        return jsonify(result)

    except Exception as e:
        print(f"BŁĄD w get_package_group: {e}")
        import traceback
        traceback.print_exc()
        return jsonify({"error": str(e)}), 500

    finally:
        if cur:
            cur.close()
        if conn:
            conn.close()


MIN_TRAINING_SAMPLES = 50  # Wymagana liczba wizyt w historii, aby AI mogło działać


@app.route('/api/ai/training-status', methods=['GET'])
@login_required
def get_ai_training_status():
    MIN_TRAINING_SAMPLES = 5  # Próg testowy

    with session_scope() as session:
        # ZMIANA: Używamy ScheduleSlot.starts_at (to jest poprawna nazwa z Twojej bazy)
        count = session.query(ScheduleSlot).filter(
            ScheduleSlot.status != 'cancelled',
            ScheduleSlot.starts_at <= datetime.now()
        ).count()

        progress = min(100, int((count / MIN_TRAINING_SAMPLES) * 100))
        is_ready = count >= MIN_TRAINING_SAMPLES

        return jsonify({
            'current_samples': count,
            'required_samples': MIN_TRAINING_SAMPLES,
            'progress': progress,
            'ready': is_ready
        })


# === THERAPISTS ===
from flask import request, jsonify
from sqlalchemy import text
from sqlalchemy.exc import IntegrityError


# Pamiętaj o importach swoich modeli i db
# from models import SessionLocal, engine, Therapist, session_scope (zależnie jak masz w projekcie)

@app.get("/api/therapists")
@login_required  # DODAJ ten dekorator!
def list_therapists():
    """Zwraca listę terapeutów bezpieczną dla Multi-tenant."""
    try:
        # 1. Pobierz firmę z sesji
        current_firma_id = session.get('firma_id', 1)
        
        # 2. Pobierz terapeutów TYLKO z tej firmy
        with SessionLocal() as s:
            therapists = (
                s.query(Therapist)
                .filter(Therapist.firma_id == current_firma_id)
                .order_by(Therapist.full_name)
                .all()
            )
            
            result = [{
                "id": t.id,
                "full_name": t.full_name,
                "specialization": t.specialization or "",
                "email": t.email or "",
                "phone": t.phone or "",
                "active": bool(t.active)
            } for t in therapists]
            
            return jsonify(result), 200

    except Exception as e:
        print(f"⚠️ Błąd w /api/therapists: {e}")
        import traceback
        traceback.print_exc()
        # Zwracamy pustą listę, żeby frontend się nie zawiesił
        return jsonify([]), 200


@app.post("/api/therapists")
@login_required
def create_therapist():
    # force=True pozwala parsować json nawet jak nagłówek Content-Type jest inny
    data = request.get_json(force=True)
    full_name = (data.get("full_name") or "").strip()

    if not full_name:
        return jsonify({"error": "Pole 'full_name' jest wymagane."}), 400

    # Używamy surowego SQL zgodnie z Twoim kodem
    sql = text("""
            INSERT INTO therapists (full_name, specialization, phone, email, active)
            VALUES (:full_name, :specialization, :phone, :email, :active)
            RETURNING id, full_name, specialization, phone, email, active;
        """)

    try:
        with engine.begin() as conn:
            row = conn.execute(sql, {
                "full_name": full_name,
                "specialization": (data.get("specialization") or None),
                "phone": (data.get("phone") or None),
                "email": (data.get("email") or None),
                "active": bool(data.get("active", True)),  # Domyślnie True
            }).mappings().first()

            # Konwersja wyniku na słownik
            result_dict = dict(row)
            return jsonify(result_dict), 201

    except IntegrityError:
        return jsonify({"error": "Taki terapeuta już istnieje (duplikat)."}), 409
    except Exception as e:
        return jsonify({"error": str(e)}), 500


@app.put('/api/therapists/<int:therapist_id>')
@login_required
def update_therapist(therapist_id):
    data = request.get_json()
    if not data:
        return jsonify({'error': 'Brak danych'}), 400

    try:
        with engine.begin() as conn:
            # 1. Pobierz stare dane
            current = conn.execute(
                text('SELECT * FROM therapists WHERE id = :id'),
                {"id": therapist_id}
            ).mappings().first()

            if not current:
                return jsonify({'error': 'Terapeuta nie znaleziony'}), 404

            # 2. Przygotuj zmiany
            update_fields = []
            params = {"id": therapist_id}
            change_details = []  # Do logowania

            # Helper do sprawdzania zmian
            def check_change(field_name, new_val, old_val, sql_col=None):
                sql_col = sql_col or field_name
                # Traktuj None i pusty string jako to samo
                if (new_val or "") != (old_val or ""):
                    update_fields.append(f"{sql_col} = :{field_name}")
                    params[field_name] = new_val
                    change_details.append(f"{field_name}: '{old_val}' -> '{new_val}'")

            # A. Full Name
            new_name = data.get('full_name', '').strip()
            if new_name:
                check_change('full_name', new_name, current['full_name'])

            # B. Phone
            if 'phone' in data:
                check_change('phone', data['phone'].strip(), current['phone'])

            # C. Email
            if 'email' in data:
                check_change('email', data['email'].strip(), current['email'])

            # D. Specialization (dodane, bo brakowało w Twoim PUT, a jest w tabeli)
            if 'specialization' in data:
                check_change('specialization', data['specialization'].strip(), current['specialization'])

            # E. Active
            if 'active' in data:
                new_active = bool(data['active'])
                old_active = bool(current['active'])
                if new_active != old_active:
                    update_fields.append("active = :active")
                    params["active"] = new_active
                    change_details.append(f"Status: {old_active} -> {new_active}")

            if not update_fields:
                return jsonify({'message': 'Brak zmian'}), 200

            # 4. Wykonaj Update
            sql = text(f"UPDATE therapists SET {', '.join(update_fields)} WHERE id = :id")
            conn.execute(sql, params)

            # 5. Logowanie (opcjonalne, zakomentowane jeśli nie masz funkcji log_activity)
            # log_activity("EDYCJA_TERAPEUTY", f"ID {therapist_id}: {', '.join(change_details)}")

            return jsonify({'success': True, 'message': 'Zaktualizowano pomyślnie'}), 200

    except Exception as e:
        print(f"Błąd PUT: {e}")
        return jsonify({'error': str(e)}), 500


@app.delete("/api/therapists/<int:tid>")
@login_required
def delete_therapist(tid):
    try:
        with session_scope() as db_session:
            therapist = db_session.query(Therapist).filter_by(id=tid, firma_id=session.get('firma_id')).first()
            if not therapist:
                return jsonify({"error": "Terapeuta nie został znaleziony."}), 404

            # Próba usunięcia
            db_session.delete(therapist)
            # Commit nastąpi automatycznie na końcu bloku

            log_activity("USUNIECIE_TERAPEUTY", f"Usunięto terapeutę ID: {tid}")
            return "", 204

    except IntegrityError as e:
        # Tutaj łapiemy błąd bazy danych (ten z Twojego zrzutu ekranu)
        error_info = str(e.orig)

        # Sprawdzamy czy błąd dotyczy tabeli 'users' (powiązane konto)
        if "users_therapist_id_fkey" in error_info or "table \"users\"" in error_info:
            return jsonify({
                "error": "Nie można usunąć: Ten terapeuta ma przypisane aktywne konto logowania. "
                         "Najpierw wejdź w 'Role i Użytkownicy' i odepnij profil terapeuty od użytkownika."
            }), 409

        # Sprawdzamy czy błąd dotyczy wizyt/historii (tabela schedule_slots, tus_sessions itp.)
        elif "schedule_slots" in error_info or "tus_" in error_info:
            return jsonify({
                "error": "Nie można usunąć: Ten terapeuta ma historię wizyt lub zajęć w systemie. "
                         "Zamiast usuwać, edytuj go i odznacz pole 'Aktywny'."
            }), 409

        # Inny błąd integralności
        return jsonify({"error": "Nie można usunąć rekordu, ponieważ jest powiązany z innymi danymi w systemie."}), 409

    except Exception as e:
        print(f"Błąd usuwania terapeuty: {e}")
        return jsonify({"error": "Wystąpił nieoczekiwany błąd serwera."}), 500


# === DRIVERS ===
# --- LISTA KIEROWCÓW (odporna na brak pola phone itd.) ---
@app.route('/api/drivers', methods=['GET'])
@login_required
def list_drivers():
    """Zwraca listę aktywnych kierowców tylko dla zalogowanej firmy."""
    # Pobieramy ID firmy z sesji
    current_firma_id = session.get('firma_id', 1)
    print(f"🔍 DEBUG: Pobieranie kierowców dla firma_id = {current_firma_id}")
    print(f"🔍 DEBUG: Zawartość sesji: {dict(session)}")
    
    try:
        with SessionLocal() as s:
            drivers = (
                s.query(Driver)
                .filter_by(active=True, firma_id=current_firma_id)  # <--- TEN FILTR!
                .filter(Driver.active == True)
                .order_by(Driver.full_name)
                .all()
            )
            
            # Ręczne mapowanie zamiast d.as_dict()
            result = [{
                "id": d.id,
                "full_name": d.full_name,
                "phone": d.phone if d.phone else "",
                "active": bool(d.active)
            } for d in drivers]
            
            return jsonify(result), 200
    except Exception as e:
        print(f"❌ Błąd pobierania kierowców: {e}")
        return jsonify([]), 200

@app.route('/api/drivers', methods=['POST'])
@login_required
def create_driver():
    """Tworzy nowego kierowcę z bezpiecznym zapisem i izolacją danych (Multi-tenant)."""
    if not (current_user.is_admin or current_user.has_permission('manage_drivers')):
        return jsonify({"error": "Brak uprawnień do zarządzania kierowcami."}), 403

    data = request.get_json(force=True) or {}
    full_name = (data.get('full_name') or '').strip()
    
    if not full_name:
        return jsonify({"error": "Imię i nazwisko kierowcy są wymagane."}), 400

    current_firma_id = session.get('firma_id', 1)

    try:
        # Przygotowujemy czyste zmienne lokalne na bezpieczną migawkę danych
        saved_id = None
        saved_name = ""

        # Blok transakcyjny bazy danych
        with session_scope() as db_session:
            new_driver = Driver(
                full_name=full_name,
                phone=(data.get('phone') or '').strip() or None,
                active=True,
                firma_id=current_firma_id  # Prawidłowe przypisanie do zalogowanej firmy
            )
            db_session.add(new_driver)
            db_session.flush()  # Wymuszamy na PostgreSQL wygenerowanie nowego ID
            
            # ROBIMY STRZELISTĄ MIGAWKĘ – zapisujemy czyste wartości tekstowe/liczbowe
            saved_id = new_driver.id
            saved_name = new_driver.full_name

        # Wywołujemy logowanie bezpiecznie POZA blokiem bazy danych
        log_activity("DODANIE_KIEROWCY", f"Dodano kierowcę: {saved_name} (ID: {saved_id}) dla firmy ID {current_firma_id}")
        
        # Zwracamy bezpieczną zmienną lokalną zamiast odpiętego obiektu ORM
        return jsonify({"success": True, "id": saved_id}), 201

    except Exception as e:
        print(f"❌ Błąd podczas tworzenia kierowcy: {e}")
        return jsonify({"error": f"Błąd wewnętrzny serwera: {str(e)}"}), 500


@app.put("/api/drivers/<int:did>")
@login_required
def update_driver(did):
    """Aktualizuje dane kierowcy."""
    with session_scope() as db_session:
        driver = db_session.query(Driver).filter_by(id=did, firma_id=session.get('firma_id')).first()
        if not driver:
            return jsonify({"error": "Kierowca nie istnieje."}), 404

        data = request.get_json(silent=True) or {}
        driver.full_name = data.get("full_name", driver.full_name)
        driver.phone = data.get("phone", driver.phone)
        driver.active = data.get("active", driver.active)
        try:
            db_session.commit()
            return jsonify({"id": driver.id, "full_name": driver.full_name}), 200
        except IntegrityError:
            db_session.rollback()
            return jsonify({"error": "Taki kierowca już istnieje (imię i nazwisko)."}), 409


@app.delete("/api/drivers/<int:did>")
@login_required
def delete_driver(did):
    """Usuwa kierowcę."""
    with session_scope() as db_session:
        driver = db_session.query(Driver).filter_by(id=did, firma_id=session.get('firma_id')).first()
        if not driver:
            return jsonify({"error": "Driver not found"}), 404
        db_session.delete(driver)
        db_session.commit()
        return "", 204


# ==========================================
# === WIDOK DLA KLIENTA (BEZ LOGOWANIA) ===
# ==========================================

@app.route('/strefa-klienta/<client_uuid>')
@login_required
def external_journal(client_uuid):
    """Widok HTML dla klienta."""
    try:
        with session_scope() as db_session:
            # SZUKAMY W NOWEJ TABELI
            user = db_session.query(DiaryUser).filter_by(public_token=client_uuid,firma_id=session.get('firma_id')).first()

            if not user:
                return "Nieprawidłowy link lub dziennik nie istnieje.", 404

            return render_template(
                'dzienniczek.html',
                client_name="Anonimowy Użytkownik",  # W tej tabeli nie mamy nazwisk
                client_token=client_uuid
            )

    except Exception as e:
        print(f"Błąd widoku: {e}")
        return "Wystąpił błąd serwera.", 500


# === CLIENT UNAVAILABILITY ===

@app.get("/api/clients/<int:client_id>/unavailability")
def get_client_unavailability(client_id):
    """Pobiera wszystkie wpisy o niedostępności dla danego klienta."""
    sql = text("""
            SELECT id, day_of_week, start_time, end_time, notes 
            FROM client_unavailability 
            WHERE client_id = :cid 
            ORDER BY day_of_week, start_time
        """)
    with engine.begin() as conn:
        rows = conn.execute(sql, {"cid": client_id}).mappings().all()
        # Konwertuj obiekty czasu na stringi dla łatwiejszej obsługi w JSON
        results = [
            {**row, 'start_time': row['start_time'].strftime('%H:%M'), 'end_time': row['end_time'].strftime('%H:%M')}
            for row in rows
        ]
        return jsonify(results)


@app.post("/api/clients/<int:client_id>/unavailability")
def add_client_unavailability(client_id):
    """Dodaje nowy wpis o niedostępności."""
    data = request.get_json(silent=True) or {}
    required = ['day_of_week', 'start_time', 'end_time']
    if not all(k in data for k in required):
        return jsonify({"error": "Brak wymaganych pól (dzień, start, koniec)."}), 400

    sql = text("""
            INSERT INTO client_unavailability (client_id, day_of_week, start_time, end_time, notes,firma_id)
            VALUES (:cid, :dow, :start, :end, :notes, :firma_id)
            RETURNING id
        """)
    with engine.begin() as conn:
        new_id = conn.execute(sql, {
            "cid": client_id,
            "dow": data['day_of_week'],
            "start": data['start_time'],
            "end": data['end_time'],
            "notes": data.get('notes'),
            "firma_id": session.get('firma_id')
        }).scalar_one()
    return jsonify({"id": new_id, **data}), 201


@app.delete("/api/unavailability/<int:entry_id>")
def delete_unavailability(entry_id):
    """Usuwa konkretny wpis o niedostępności."""
    sql = text("DELETE FROM client_unavailability WHERE id = :id")
    with engine.begin() as conn:
        result = conn.execute(sql, {"id": entry_id})
    if result.rowcount == 0:
        return jsonify({"error": "Nie znaleziono wpisu."}), 404
    log_activity(f"Usunięto dostępność klienta:,{entry_id}")
    return "", 204


@app.get("/api/unavailability/existing-ids")
def get_existing_unavailability_ids():
    """Zwraca listę ID klientów, którzy mają już zdefiniowaną niedostępność."""
    sql = text("SELECT DISTINCT client_id FROM client_unavailability")
    with engine.begin() as conn:
        # scalars().all() sprawi, że otrzymasz prostą listę: [1, 2, 5], a nie listę obiektów
        ids = conn.execute(sql).scalars().all()
        return jsonify(ids)


@app.post("/api/ai/plan-day")
def ai_plan_day():
    """
        Body:
        {
          "date": "2025-08-21",
          "clients": [1,2,3],
          "slot_template": {"start":"09:00","end":"10:00"}  # opcjonalnie
        }
        """
    data = request.get_json(silent=True) or {}
    date = data.get("date")
    clients = data.get("clients") or []
    if not date or not clients:
        return jsonify({"error": "date and clients[] required"}), 400

    # dla każdego klienta: TOP1 terapeuta i TOP1 kierowca z /api/ai/recommend
    # + szybka kontrola kolizji godzinowej (tu: ta sama godzina)
    plans = []
    hour_start = 9
    for cid in clients:
        rec = app.test_client().get(f"/api/ai/recommend?client_id={cid}&date={date}").get_json()
        th = (rec.get("therapists") or [{}])[0]
        dr = (rec.get("drivers") or [{}])[0]
        start = f"{date}T{str(hour_start).zfill(2)}:00:00"
        end = f"{date}T{str(hour_start + 1).zfill(2)}:00:00"
        plans.append({
            "client_id": cid,
            "therapist_id": th.get("therapist_id"),
            "driver_id_pickup": dr.get("driver_id"),
            "driver_id_dropoff": dr.get("driver_id"),
            "starts_at": start, "ends_at": end,
            "score_therapist": th.get("score"), "score_driver": dr.get("score")
        })
        hour_start += 1  # prosta sekwencja – zamienisz na CP-SAT
    return jsonify({"date": date, "proposals": plans}), 200



@app.get("/api/groups/<string:gid>")
@login_required
def get_group(gid):
    """Pobiera dane pojedynczego pakietu indywidualnego do edycji."""

    # Używamy rzutowania ::text, aby bezpiecznie łączyć UUID ze Stringami
    sql = text("""
        SELECT 
            eg.client_id, eg.label, ss.id as slot_id, ss.kind, ss.therapist_id, ss.driver_id,
            ss.vehicle_id, ss.starts_at, ss.ends_at, ss.place_from,
            ss.place_to, ss.status
        FROM event_groups eg
        JOIN schedule_slots ss ON eg.id::text = ss.group_id::text
        WHERE eg.id::text = :gid
    """)

    try:
        with engine.begin() as conn:
            # Wymuszamy string, żeby baza nie narzekała na typy
            rows = conn.execute(sql, {"gid": str(gid)}).mappings().all()

        if not rows:
            return jsonify({"error": "Pakiet nie został znaleziony w bazie."}), 404

        result = {
            "group_id": gid,
            "client_id": rows[0]['client_id'],
            "label": rows[0]['label'],
            "status": rows[0]['status'],
            "therapy": None, "pickup": None, "dropoff": None
        }

        for row in rows:
            slot_data = {
                "slot_id": row['slot_id'],
                "starts_at": row['starts_at'].isoformat() if row['starts_at'] else None,
                "ends_at": row['ends_at'].isoformat() if row['ends_at'] else None,
                "from": row['place_from'],
                "to": row['place_to'],
                "status": row['status']
            }

            if row['kind'] == 'therapy':
                result['therapy'] = {**slot_data, "therapist_id": row['therapist_id'], "place": row['place_to']}
            elif row['kind'] == 'pickup':
                result['pickup'] = {**slot_data, "driver_id": row['driver_id'], "vehicle_id": row['vehicle_id']}
            elif row['kind'] == 'dropoff':
                result['dropoff'] = {**slot_data, "driver_id": row['driver_id'], "vehicle_id": row['vehicle_id']}

        return jsonify(result), 200

    except Exception as e:
        print(f"Błąd pobierania pakietu (get_group): {e}")
        import traceback
        traceback.print_exc()
        return jsonify({"error": f"Wystąpił błąd serwera: {str(e)}"}), 500


@app.delete("/api/groups/<string:gid>")
@login_required
def delete_group(gid):
    """Usuwa cały pakiet indywidualny (rekord z event_groups i kaskadowo sloty)."""
    with engine.begin() as conn:
        result = conn.execute(text("DELETE FROM event_groups WHERE id = CAST(:gid AS UUID)"), {"gid": gid})

    if result.rowcount == 0:
        return jsonify({"error": "Pakiet nie został znaleziony lub już został usunięty."}), 404

    log_activity(f"Usunięto pakiet o numerze ID:,{gid}")

    return jsonify({"message": "Pakiet został pomyślnie usunięty."}), 200


@app.put("/api/groups/<string:gid>")
def update_group(gid):
    data = request.get_json(silent=True) or {}
    label = data.get("label")
    status = data.get("status", "planned")
    therapy = data.get("therapy")
    pickup = data.get("pickup")
    dropoff = data.get("dropoff")

    # NOWA, LEPSZA WALIDACJA DANYCH
    if not all(k in (therapy or {}) for k in ["therapist_id", "starts_at", "ends_at"]):
        return jsonify({"error": "Brak kompletnych danych terapii (terapeuta, start, koniec)."}), 400
    # KONIEC NOWEJ WALIDACJI

    try:
        with engine.begin() as conn:
            ok = conn.execute(text("SELECT 1 FROM event_groups WHERE id=:gid"), {"gid": gid}).scalar()
            if not ok: return jsonify({"error": "Nie znaleziono grupy."}), 404

            conn.execute(text("UPDATE event_groups SET label=:label WHERE id=:gid"), {"label": label, "gid": gid})

            ts = datetime.fromisoformat(therapy["starts_at"]).replace(tzinfo=TZ)
            te = datetime.fromisoformat(therapy["ends_at"]).replace(tzinfo=TZ)
            session_id = ensure_shared_session_id_for_therapist(conn, int(therapy["therapist_id"]), ts, te)

            ex = conn.execute(text("SELECT id FROM schedule_slots WHERE group_id=:gid AND kind='therapy' LIMIT 1"),
                              {"gid": gid}).mappings().first()
            if ex:
                conn.execute(text("""
                        UPDATE schedule_slots SET therapist_id=:tid, starts_at=:s, ends_at=:e, place_to=:place, status=:status, session_id=:sid WHERE id=:id
                    """), {"tid": therapy["therapist_id"], "s": ts, "e": te, "place": therapy.get("place"),
                           "status": status, "sid": session_id, "id": ex["id"]})
            else:
                conn.execute(text("""
                        INSERT INTO schedule_slots (group_id, client_id, therapist_id, kind, starts_at, ends_at, place_to, status, session_id)
                        SELECT :gid, client_id, :tid, 'therapy', :s, :e, :place, :status, :sid FROM schedule_slots WHERE group_id=:gid LIMIT 1
                    """), {"gid": gid, "tid": therapy["therapist_id"], "s": ts, "e": te, "place": therapy.get("place"),
                           "status": status, "sid": session_id})

            # POPRAWKA: Definicja funkcji przeniesiona na właściwy poziom
            def upsert_run(kind, block):
                ex = conn.execute(text("SELECT id FROM schedule_slots WHERE group_id=:gid AND kind=:kind LIMIT 1"),
                                  {"gid": gid, "kind": kind}).mappings().first()

                if block is None:
                    if ex: conn.execute(text("DELETE FROM schedule_slots WHERE id=:id"), {"id": ex["id"]})
                    return

                # POPRAWKA: Oblicz dystans PRZED tworzeniem payload
                distance = get_route_distance(block.get("from"), block.get("to"))

                s = datetime.fromisoformat(block["starts_at"]).replace(tzinfo=TZ)
                e = datetime.fromisoformat(block["ends_at"]).replace(tzinfo=TZ)

                payload = {
                    "did": block["driver_id"],
                    "veh": block.get("vehicle_id"),
                    "s": s,
                    "e": e,
                    "from": block.get("from"),
                    "to": block.get("to"),
                    "status": status,
                    "gid": gid,
                    "kind": kind,
                    "distance": distance
                }

                if ex:
                    conn.execute(text("""
                            UPDATE schedule_slots 
                            SET driver_id=:did, vehicle_id=:veh, starts_at=:s, ends_at=:e, 
                                place_from=:from, place_to=:to, status=:status, 
                                distance_km=:distance
                            WHERE id=:id
                        """), {**payload, "id": ex["id"]})
                else:
                    conn.execute(text("""
                            INSERT INTO schedule_slots 
                            (group_id, client_id, driver_id, vehicle_id, kind, starts_at, ends_at, 
                             place_from, place_to, status, distance_km)
                            SELECT :gid, client_id, :did, :veh, :kind, :s, :e, 
                                   :from, :to, :status, :distance 
                            FROM schedule_slots 
                            WHERE group_id=:gid AND kind='therapy' LIMIT 1
                        """), payload)

            upsert_run("pickup", pickup)
            upsert_run("dropoff", dropoff)

        return jsonify({"ok": True, "group_id": gid}), 200
    except IntegrityError as e:
        if getattr(e.orig, "pgcode", None) == errorcodes.FOREIGN_KEY_VIOLATION:
            return jsonify({"error": "Naruszenie klucza obcego – sprawdź ID osób/pojazdu."}), 400
        return jsonify({"error": "Błąd bazy", "details": str(e.orig)}), 400


# === TUS API ENDPOINTS ===

def get_semester_dates(school_year_start, semester):
    """Zwraca datę początkową i końcową dla danego semestru roku szkolnego."""
    if semester == 1:  # I Półrocze (Wrzesień - Styczeń)
        start_date = date(school_year_start, 9, 1)
        end_date = date(school_year_start + 1, 2, 1)  # Kończy się przed 1 lutego
    elif semester == 2:  # II Półrocze (Luty - Czerwiec)
        start_date = date(school_year_start + 1, 2, 1)
        end_date = date(school_year_start + 1, 7, 1)  # Kończy się przed 1 lipca
    else:
        raise ValueError("Semester must be 1 or 2")
    return start_date, end_date


@app.get("/api/tus/groups")
@login_required
def get_tus_groups():
    with session_scope() as db_session:
        # POPRAWKA 500 ERROR:
        # SQLAlchemy nie potrafi bezpośrednio złączyć 'association_proxy' (TUSGroup.members).
        # Musimy odwołać się do fizycznej relacji: member_associations -> client
        groups = db_session.query(TUSGroup).options(
            joinedload(TUSGroup.therapist),
            joinedload(TUSGroup.member_associations).joinedload(TUSGroupMember.client),
            joinedload(TUSGroup.sessions)
        ).order_by(TUSGroup.name).all()

        result = [{
            "id": group.id,
            "name": group.name,
            "therapist_id": group.therapist.id if group.therapist else None,
            "therapist_name": group.therapist.full_name if group.therapist else "Brak",
            "member_count": len(group.members),
            "total_bonuses": sum(s.bonuses_awarded for s in group.sessions if s.bonuses_awarded)
        } for group in groups]
        return jsonify(result)


@app.post("/api/tus/groups")
@login_required
def create_tus_group():
    data = request.get_json(silent=True) or {}

    # Walidacja danych wejściowych
    name = (data.get("name") or "").strip()
    therapist_id = data.get("therapist_id")

    if not name or not therapist_id:
        return jsonify({"error": "Nazwa grupy i terapeuta są wymagani."}), 400

    with session_scope() as db_session:
        # --- ZABEZPIECZENIE PRZED DUPLIKATEM (Case Insensitive) ---
        # Sprawdzamy, czy istnieje grupa o takiej samej nazwie (ignorując wielkość liter)
        existing_group = db_session.query(TUSGroup).filter(
            func.lower(TUSGroup.name) == name.lower()
        ).first()

        if existing_group:
            return jsonify({"error": f"Grupa o nazwie '{name}' już istnieje."}), 409
        # ----------------------------------------------------------

        client_ids = [int(cid) for cid in data.get("client_ids", []) if cid is not None]
        members = []
        if client_ids:
            members = db_session.query(Client).filter(Client.id.in_(client_ids)).all()

        new_group = TUSGroup(
            name=name,
            therapist_id=therapist_id,
            assistant_therapist_id=data.get("assistant_therapist_id"),
            members=members
        )
        db_session.add(new_group)
        db_session.flush()  # Nadaje ID

        log_activity("UTWORZENIE_GRUPY_TUS", f"Utworzono grupę: {name} (ID: {new_group.id})")

        return jsonify({"id": new_group.id, "name": new_group.name}), 201


@app.put('/api/tus/groups/<int:group_id>')
@login_required
def update_tus_group(group_id):
    data = request.get_json()
    if not data:
        return jsonify({'error': 'Brak danych'}), 400

    try:
        with session_scope() as session:
            # 1. Pobierz grupę
            group = session.query(TUSGroup).filter_by(id=group_id).first()
            if not group:
                return jsonify({'error': 'Grupa nie znaleziona'}), 404

            # 2. Aktualizacja nazwy z WALIDACJĄ DUPLIKATÓW
            if 'name' in data:
                new_name = data['name'].strip()
                if new_name:
                    duplicate = session.query(TUSGroup).filter(
                        func.lower(TUSGroup.name) == new_name.lower(),
                        TUSGroup.id != group_id  # Ignorujemy samą siebie
                    ).first()

                    if duplicate:
                        return jsonify({'error': f"Nazwa '{new_name}' jest już zajęta przez inną grupę."}), 409

                    group.name = new_name

            # 3. Aktualizacja terapeutów
            if 'therapist_id' in data:
                tid = data['therapist_id']
                group.therapist_id = int(tid) if tid else None

            if 'assistant_therapist_id' in data:
                atid = data['assistant_therapist_id']
                group.assistant_therapist_id = int(atid) if atid else None

            # 4. BEZPIECZNA AKTUALIZACJA CZŁONKÓW (SOFT DELETE + DATY)
            if 'client_ids' in data:
                new_client_ids = set(int(cid) for cid in data['client_ids'] if cid)
                
                # Krok A: Znajdź obecnych, aktywnych członków tej grupy
                current_active_members = session.query(TUSGroupMember).filter_by(
                    group_id=group_id, 
                    is_active=True
                ).all()
                current_active_ids = {m.client_id for m in current_active_members}

                # Krok B: Kto został usunięty z listy? (Soft-delete)
                to_remove = current_active_ids - new_client_ids
                for member in current_active_members:
                    if member.client_id in to_remove:
                        member.is_active = False
                        # Ustawiamy datę odejścia na dzisiaj (lub pobieramy z danych, jeśli przesłano)
                        member.leave_date = date.today()

                # Krok C: Kto został dodany do listy? (Nowe lub reaktywacja)
                to_add = new_client_ids - current_active_ids
                for cid in to_add:
                    # Sprawdź, czy istnieje historyczny wpis (nieaktywny)
                    existing_member = session.query(TUSGroupMember).filter_by(
                        group_id=group_id, 
                        client_id=cid
                    ).first()

                    if existing_member:
                        # Jeśli wracał do grupy po latach - reaktywujemy wpis
                        existing_member.is_active = True
                        existing_member.join_date = date.today()
                        existing_member.leave_date = None
                    else:
                        # Zupełnie nowe dziecko w grupie
                        new_member = TUSGroupMember(
                            group_id=group_id,
                            client_id=cid,
                            is_active=True,
                            join_date=date.today(),
                            firma_id=session.get('firma_id', 1)
                        )
                        session.add(new_member)

            # Session_scope() automatycznie wykona commit() na końcu bloku 'with'

            # Zapisujemy wynik do słownika przed wyjściem z sesji
            result = {
                "id": group.id,
                "name": group.name,
                "message": "Zaktualizowano pomyślnie"
            }

        return jsonify(result), 200

    except Exception as e:
        print(f"❌ Błąd aktualizacji grupy TUS: {e}")
        import traceback
        traceback.print_exc()
        return jsonify({'error': str(e)}), 500
        
@app.post('/api/tus/members/transfer')
@login_required
def transfer_tus_member():
    """
    Przenosi klienta z jednej grupy TUS do drugiej,
    zachowując HISTORIĘ (soft delete w starej grupie + insert w nowej).
    """
    data = request.get_json(silent=True) or {}
    client_id = data.get('client_id')
    from_group_id = data.get('from_group_id')
    to_group_id = data.get('to_group_id')
    transfer_date_str = data.get('transfer_date')  # YYYY-MM-DD, opcjonalnie

    if not client_id or not to_group_id:
        return jsonify({"error": "client_id i to_group_id są wymagane"}), 400

    try:
        transfer_date = date.today()
        if transfer_date_str:
            transfer_date = datetime.strptime(transfer_date_str, '%Y-%m-%d').date()
    except ValueError:
        return jsonify({"error": "Nieprawidłowy format daty (YYYY-MM-DD)"}), 400

    try:
        with session_scope() as db_session:
            # 1. Sprawdź czy klient istnieje
            client = db_session.get(Client, client_id)
            if not client:
                return jsonify({"error": "Klient nie istnieje"}), 404

            # 2. Sprawdź czy grupa docelowa istnieje
            to_group = db_session.get(TUSGroup, to_group_id)
            if not to_group:
                return jsonify({"error": "Grupa docelowa nie istnieje"}), 404

            # 3. Jeśli podano from_group_id - zamknij członkostwo w starej grupie
            if from_group_id:
                old_membership = db_session.query(TUSGroupMember).filter_by(
                    group_id=from_group_id,
                    client_id=client_id
                ).first()

                if old_membership:
                    # SOFT DELETE - nie usuwamy wiersza!
                    old_membership.is_active = False
                    old_membership.leave_date = transfer_date
                    print(f"✅ Zamknięto członkostwo klienta {client.full_name} w grupie TUS-{from_group_id}")

            # 4. Dodaj / reaktywuj członkostwo w nowej grupie
            new_membership = db_session.query(TUSGroupMember).filter_by(
                group_id=to_group_id,
                client_id=client_id
            ).first()

            if new_membership:
                # Jeśli już istnieje (historycznie) - reaktywuj
                new_membership.is_active = True
                new_membership.join_date = transfer_date
                new_membership.leave_date = None
                print(f"♻️ Reaktywowano historyczne członkostwo w grupie TUS-{to_group_id}")
            else:
                new_membership = TUSGroupMember(
                    group_id=to_group_id,
                    client_id=client_id,
                    is_active=True,
                    join_date=transfer_date,
                    leave_date=None,
                    firma_id=session.get('firma_id', 1)
                )
                db_session.add(new_membership)
                print(f"➕ Dodano nowe członkostwo w grupie TUS-{to_group_id}")

            # 5. Log
            log_activity(
                "PRZENIESIENIE_TUS",
                f"Klient {client.full_name} (ID:{client_id}) przeniesiony "
                f"z grupy {from_group_id or '?'} do {to_group_id} w dniu {transfer_date}"
            )

        return jsonify({
            "success": True,
            "message": f"Klient {client.full_name} przeniesiony.",
            "client_id": client_id,
            "from_group_id": from_group_id,
            "to_group_id": to_group_id,
            "transfer_date": transfer_date.isoformat()
        }), 200

    except Exception as e:
        print(f"❌ Błąd przeniesienia: {e}")
        import traceback
        traceback.print_exc()
        return jsonify({"error": str(e)}), 500


# --- GENEROWANIE PODSUMOWANIA TUS (AI) ---
@app.route('/api/tus/groups/<int:group_id>/generate-summary', methods=['POST'])
@login_required
def generate_tus_summary(group_id):
    data = request.get_json()
    start_date_str = data.get('start_date')
    end_date_str = data.get('end_date')

    if not start_date_str or not end_date_str:
        return jsonify({'error': 'Podaj zakres dat'}), 400

    try:
        with session_scope() as session:
            # 1. Pobierz Grupę
            group = session.query(TUSGroup).get(group_id)
            if not group:
                return jsonify({'error': 'Grupa nie istnieje'}), 404

            # --- POPRAWKA TUTAJ ---
            # Pobieramy nazwę terapeuty bezpiecznie przez relację
            therapist_name = "Nie podano"
            if group.therapist:
                therapist_name = group.therapist.full_name
            # ----------------------

            # 2. Pobierz PLAN w tym okresie
            plan_items = session.query(TUSPlanItem).filter(
                TUSPlanItem.group_id == group_id,
                TUSPlanItem.planned_date >= start_date_str,
                TUSPlanItem.planned_date <= end_date_str
            ).order_by(TUSPlanItem.planned_date).all()

            # 3. Pobierz SESJE (Rzeczywistość) w tym okresie
            sessions = session.query(TUSSession).filter(
                TUSSession.group_id == group_id,
                TUSSession.session_date >= start_date_str,
                TUSSession.session_date <= end_date_str
            ).order_by(TUSSession.session_date).all()

            # --- PRZYGOTOWANIE DANYCH DLA AI ---

            # Formatowanie planu
            plan_text = ""
            if not plan_items:
                plan_text = "Brak wpisów w planie na ten okres."
            else:
                for p in plan_items:
                    status = "ZREALIZOWANO" if p.is_executed else "NIEZREALIZOWANO"
                    plan_text += f"- {p.planned_date}: {p.topic} ({status})\n"

            # Formatowanie sesji (Rzeczywistość)
            sessions_text = ""
            total_attendance = 0
            count_sessions = len(sessions)

            if not sessions:
                sessions_text = "Nie przeprowadzono żadnych sesji w tym okresie."
            else:
                for s in sessions:
                    # Obliczanie frekwencji na sesji
                    present_count = session.query(TUSSessionAttendance).filter_by(session_id=s.id,
                                                                                  status='obecny').count()
                    total_attendance += present_count

                    # Pobranie tematu
                    topic_title = s.topic.title if s.topic else 'Bez tematu'
                    sessions_text += f"- {s.session_date}: {topic_title} (Obecnych: {present_count})\n"

            # 4. KOMUNIKACJA Z GEMINI
            import google.generativeai as genai
            api_key = os.getenv("GOOGLE_AI_API_KEY")
            if not api_key:
                return jsonify({'error': 'Brak klucza API Google'}), 500

            genai.configure(api_key=api_key)
            model = genai.GenerativeModel('gemini-3.5-flash')

            prompt = f"""
            Jesteś doświadczonym terapeutą TUS (Trening Umiejętności Społecznych).
            Przygotuj profesjonalne sprawozdanie okresowe (podsumowanie) dla grupy.

            DANE GRUPY:
            Nazwa: {group.name}
            Terapeuta: {therapist_name}
            Okres: {start_date_str} do {end_date_str}
            Liczba zrealizowanych spotkań: {count_sessions}

            PLAN PRACY (To co było zamierzone):
            {plan_text}

            REALIZACJA (To co się faktycznie odbyło):
            {sessions_text}

            INSTRUKCJA:
            Napisz podsumowanie w formacie HTML (użyj znaczników <h3>, <p>, <ul>, <li>, <strong>).
            Nie dodawaj znaczników ```html na początku ani końcu. Tylko czysty kod wewnątrz body.

            Struktura raportu:
            1. Wstęp (informacja o grupie i okresie, ogólny cel).
            2. Realizacja Tematyki (Opisz, czy udało się zrealizować plan, jakie tematy dominowały. Jeśli były rozbieżności między planem a realizacją, wspomnij o tym delikatnie jako "dostosowanie do potrzeb grupy").
            3. Statystyki i Frekwencja (Ogólne podsumowanie zaangażowania na podstawie liczby sesji i obecności).
            4. Wnioski i Rekomendacje (Na podstawie tematów - np. jeśli dużo było o emocjach, napisz że grupa pracowała nad sferą emocjonalną. Zaproponuj kontynuację pracy).

            Styl: Formalny, ale empatyczny. Język polski.
            """

            response = model.generate_content(prompt)
            report_html = response.text.strip().replace('```html', '').replace('```', '')

            return jsonify({'report': report_html})

    except Exception as e:
        print(f"Błąd generowania raportu: {e}")
        import traceback
        traceback.print_exc()
        return jsonify({'error': str(e)}), 500

@app.post("/api/tus/sessions")
@login_required
def create_tus_session():
    data = request.get_json(silent=True) or {}
    print(f"=== ROZPOCZĘCIE TWORZENIA SESJI TUS ===")

    saved_session_id = None

    try:
        # --- WALIDACJA ---
        if not data.get("group_id"):
            return jsonify({"error": "Brak ID grupy."}), 400

        group_id = int(data["group_id"])

        topic_title = (data.get("topic_title") or "").strip()
        if not topic_title:
            return jsonify({"error": "Temat zajęć jest wymagany."}), 400

        session_date_str = data.get("session_date")
        if not session_date_str:
            return jsonify({"error": "Brak daty sesji."}), 400

        try:
            # Parsowanie daty
            dt_obj = datetime.fromisoformat(session_date_str.replace('Z', ''))
            sess_date = dt_obj.date()  # To jest obiekt daty (YYYY-MM-DD)
            sess_time = dt_obj.time()
        except (ValueError, TypeError):
            return jsonify({"error": f"Błąd formatu daty: {session_date_str}"}), 400

        behavior_ids = [int(bid) for bid in data.get("behavior_ids", []) if bid]
        present_client_ids_list = [int(cid) for cid in data.get("present_client_ids", []) if cid]
        present_client_ids_set = set(present_client_ids_list)

        # --- OPERACJE NA BAZIE ---
        with session_scope() as db_session:

            # 1. LOGIKA TEMATU (Znajdź lub utwórz)
            topic = db_session.query(TUSTopic).filter(
                func.lower(func.trim(TUSTopic.title)) == func.lower(topic_title)
            ).first()

            if not topic:
                topic = TUSTopic(title=topic_title)
                db_session.add(topic)
                try:
                    db_session.flush()
                except IntegrityError:
                    db_session.rollback()
                    topic = db_session.query(TUSTopic).filter(
                        func.lower(TUSTopic.title) == func.lower(topic_title)
                    ).first()
                    if not topic:
                        raise Exception("Błąd bazy danych przy tworzeniu tematu.")

            topic_id_for_session = topic.id

            # 2. LOGIKA REALIZACJI PLANU (ULEPSZONA)
            plan_item_id = data.get('plan_item_id')  # Nowy parametr z frontendu

            if plan_item_id:
                # Opcja A: Mamy konkretne ID (pewniak)
                plan_item = db_session.get(TUSPlanItem, int(plan_item_id))
                if plan_item:
                    plan_item.is_executed = True
                    print(f"✅ Oznaczono plan (ID: {plan_item_id}) jako wykonany (na podstawie ID).")
            else:
                # Opcja B: Fallback (szukamy po dacie, jeśli nie przekazano ID)
                plan_item = db_session.query(TUSPlanItem).filter(
                    TUSPlanItem.group_id == group_id,
                    TUSPlanItem.planned_date == sess_date
                ).first()

                if plan_item:
                    plan_item.is_executed = True
                    print(f"✅ Oznaczono plan z dnia {sess_date} jako wykonany (na podstawie daty).")

            # 3. TWORZENIE SESJI
            new_session = TUSSession(
                group_id=group_id,
                topic_id=topic_id_for_session,
                session_date=sess_date,
                session_time=sess_time,
            )
            db_session.add(new_session)
            db_session.flush()  # Nadaje ID

            saved_session_id = new_session.id

            # 4. ZACHOWANIA
            if behavior_ids:
                behaviors_info = db_session.query(TUSBehavior).filter(TUSBehavior.id.in_(behavior_ids)).all()
                behaviors_map = {b.id: b.default_max_points for b in behaviors_info}

                for b_id in behavior_ids:
                    session_behavior = TUSSessionBehavior(
                        session_id=saved_session_id,
                        behavior_id=b_id,
                        max_points=behaviors_map.get(b_id, 3)
                    )
                    db_session.add(session_behavior)

            # 5. OBECNOŚĆ
            all_group_members = db_session.query(TUSGroupMember).filter(TUSGroupMember.group_id == group_id).all()

            attendance_objects = []
            for member in all_group_members:
                status = 'obecny' if member.client_id in present_client_ids_set else 'nieobecny'
                attendance_objects.append(TUSSessionAttendance(
                    session_id=saved_session_id,
                    client_id=member.client_id,
                    status=status
                ))

            if attendance_objects:
                db_session.add_all(attendance_objects)

            # Logowanie
            try:
                # Tu zakładam, że masz funkcję log_activity
                # log_activity("UTWORZONO_SESJE_TUS", f"Sesja ID={saved_session_id}...")
                pass
            except:
                pass

        # Sukces
        print(f"✅ Sukces. Utworzono sesję ID: {saved_session_id}")
        return jsonify({"id": saved_session_id}), 201

    except Exception as e:
        error_msg = str(e)
        print(f"❌ BŁĄD: {error_msg}")
        import traceback
        traceback.print_exc()
        return jsonify({"error": f"Błąd serwera: {error_msg}"}), 500


# Endpoint do serwowania plików (jeśli jeszcze go nie masz)
@app.route('/uploads/<path:folder>/<path:filename>')
def serve_uploaded_file(folder, filename):
    # Proste zabezpieczenie, aby nie wyjść poza folder 'uploads'
    safe_path = os.path.normpath(os.path.join('uploads', folder, filename))

    # Sprawdzenie, czy ścieżka nadal jest w folderze 'uploads'
    if not safe_path.startswith(os.path.normpath('uploads') + os.sep):
        return "Forbidden", 403

    return send_from_directory(os.path.dirname(safe_path), os.path.basename(safe_path))


@app.put("/api/tus/sessions/<int:session_id>")
def update_tus_session(session_id):
    data = request.get_json(silent=True) or {}
    print(f"=== AKTUALIZACJA SESJI {session_id} ===")
    print(f"Otrzymane dane: {data}")

    with session_scope() as db_session:
        s = db_session.get(TUSSession, session_id)
        if not s:
            return jsonify({"error": "Session not found"}), 404

        # --- 1. Aktualizacja podstawowych pól ---
        if "topic_id" in data:
            s.topic_id = data["topic_id"]
        if "bonuses_awarded" in data:
            s.bonuses_awarded = int(data["bonuses_awarded"])

        if "session_date" in data:
            try:
                dt = datetime.fromisoformat(data["session_date"])
                s.session_date = dt.date()
                s.session_time = dt.time()
            except (ValueError, TypeError):
                return jsonify({"error": "Nieprawidłowy format daty."}), 400

        # --- 2. Aktualizacja ZACHOWAŃ (to nie działało wcześniej) ---
        if "behavior_ids" in data:
            print(f"Aktualizuję zachowania dla sesji {session_id}...")
            # Usuń stare przypisania
            db_session.query(TUSSessionBehavior).filter_by(session_id=session_id).delete()

            new_b_ids = data["behavior_ids"]
            if new_b_ids:
                # Pobierz domyślne punkty dla nowych zachowań
                behaviors_map = {
                    b.id: b.default_max_points
                    for b in db_session.query(TUSBehavior).filter(TUSBehavior.id.in_(new_b_ids)).all()
                }
                # Dodaj nowe
                for bid in new_b_ids:
                    db_session.add(TUSSessionBehavior(
                        session_id=session_id,
                        behavior_id=bid,
                        max_points=behaviors_map.get(bid, 3)
                    ))
            print(f"Zapisano {len(new_b_ids)} nowych zachowań.")

        # --- 3. Aktualizacja OBECNOŚCI (to też warto naprawić przy okazji) ---
        if "present_client_ids" in data:
            print(f"Aktualizuję obecność dla sesji {session_id}...")
            # Usuń starą obecność
            db_session.query(TUSSessionAttendance).filter_by(session_id=session_id).delete()

            # Pobierz wszystkich członków grupy, aby ustawić też status 'nieobecny'
            all_members = db_session.query(TUSGroupMember).filter_by(group_id=s.group_id).all()
            present_set = set(data["present_client_ids"])

            for member in all_members:
                status = 'obecny' if member.client_id in present_set else 'nieobecny'
                db_session.add(TUSSessionAttendance(
                    session_id=session_id,
                    client_id=member.client_id,
                    status=status
                ))
            print("Zaktualizowano listę obecności.")

        return jsonify({"ok": True}), 200


@app.delete("/api/tus/sessions/<int:session_id>")
@login_required
def delete_tus_session(session_id):
    # Odczytujemy decyzję użytkownika z parametrów URL
    delete_all_bonuses = request.args.get('delete_all_bonuses', 'false').lower() == 'true'

    with session_scope() as db_session:
        # Znajdź sesję, którą chcemy usunąć
        session_to_delete = db_session.get(TUSSession, session_id)
        if not session_to_delete:
            return jsonify({"error": "Session not found"}), 404

        group_id = session_to_delete.group_id

        # --- NOWA LOGIKA DECYZYJNA ---
        if delete_all_bonuses:
            # Użytkownik wybrał "TAK": usuń WSZYSTKIE bonusy w tej grupie
            print(f"DIAGNOSTYKA: Usuwanie wszystkich bonusów dla grupy ID: {group_id}")

            # 1. Usuń bonusy ogólne
            db_session.query(TUSGeneralBonus).filter(TUSGeneralBonus.group_id == group_id).delete()

            # 2. Usuń bonusy sesyjne (ze wszystkich sesji w tej grupie)
            session_ids_in_group = db_session.query(TUSSession.id).filter(TUSSession.group_id == group_id)
            db_session.query(TUSMemberBonus).filter(TUSMemberBonus.session_id.in_(session_ids_in_group)).delete()

        # Niezależnie od decyzji, ZAWSZE usuwamy sesję.
        # Jeśli użytkownik wybrał "NIE", kaskada w bazie danych usunie
        # bonusy i punkty TYLKO dla tej jednej usuwanej sesji.
        db_session.delete(session_to_delete)
        # --- POPRAWIONE LOGOWANIE ---
        # 1. Budujemy treść zależnie od tego, co się stało
        info_bonusy = "Usunięto WSZYSTKIE punkty grupy" if delete_all_bonuses else "Zachowano punkty innych sesji"

        # 2. Wywołujemy log z dwoma argumentami (Akcja, Szczegóły)
        log_activity(
            "USUNIECIE_SESJI_TUS",
            f"Sesja ID: {session_id}, Grupa ID: {group_id}. Decyzja: {info_bonusy}"
        )
    return jsonify({"ok": True}), 200


@app.put("/api/tus/groups/<int:gid>/target")
@login_required
def tus_update_targets(gid):
    data = request.get_json(silent=True) or {}
    try:
        school_year_start = int(data["school_year_start"])
        semester = int(data["semester"])
        points = int(data["points"])
        reward = (data.get("reward") or "").strip()
    except (KeyError, ValueError, TypeError):
        return jsonify({"error": "Brakujące lub nieprawidłowe dane."}), 400

    with session_scope() as db_session:
        target = db_session.query(TUSGroupTarget).filter_by(
            group_id=gid,
            school_year_start=school_year_start,
            semester=semester
        ).first()

        if target:  # Aktualizuj istniejący
            target.target_points = points
            target.reward = reward
        else:  # Stwórz nowy
            # --- POCZĄTEK POPRAWKI ---
            target = TUSGroupTarget()  # Stwórz pusty obiekt
            # Ustaw wartości jako atrybuty
            target.group_id = gid
            target.school_year_start = school_year_start
            target.semester = semester
            target.target_points = points
            target.reward = reward
            db_session.add(target)
            # --- KONIEC POPRAWKI ---
        # LOGOWANIE (Poprawione)
        log_activity(
            "EDYCJA_CELOW_TUS",
            f"Grupa ID: {gid}, Rok: {school_year_start}, Semestr: {semester}. Ustawiono: {points} pkt, Nagroda: '{reward}'"
        )
    return jsonify({"ok": True})


@app.get("/api/tus/groups/<int:group_id>")
def get_tus_group_details(group_id: int):
    with session_scope() as db_session:
        group = db_session.query(TUSGroup).options(
            joinedload(TUSGroup.therapist),
            joinedload(TUSGroup.assistant_therapist),
            joinedload(TUSGroup.member_associations).joinedload(TUSGroupMember.client),
            # Use 'selectinload' for efficient and correct loading of the session list
            selectinload(TUSGroup.sessions).joinedload(TUSSession.topic)
        ).filter(TUSGroup.id == group_id).first()

        if not group:
            return jsonify({"error": "Group not found"}), 404

        # Manually build the JSON response to guarantee correct date format
        sessions_json = sorted([
            {
                "id": s.id,
                "session_date": s.session_date.isoformat() if s.session_date else None,
                "session_time": s.session_time.strftime('%H:%M:%S') if s.session_time else None,
                "topic_title": s.topic.title if s.topic else "bez tematu",
                "bonuses_awarded": s.bonuses_awarded or 0
            } for s in group.sessions
        ], key=lambda x: (x.get('session_date') or "", x.get('session_time') or ""), reverse=True)

        members_json = [{"id": m.id, "full_name": m.full_name} for m in group.members]

        group_data = {
            "id": group.id,
            "name": group.name,
            "therapist_id": group.therapist_id,
            "therapist_name": group.therapist.full_name if group.therapist else "Brak",
            "assistant_therapist_id": group.assistant_therapist_id,
            "assistant_therapist_name": group.assistant_therapist.full_name if group.assistant_therapist else None,
            "members": members_json,
            "sessions": sessions_json,
            "schedule_days": [d.isoformat() for d in group.schedule_days] if group.schedule_days else []
        }

        return jsonify(group_data)


@app.get('/api/tus/groups/<int:group_id>/bonuses')
@login_required
def get_group_bonuses_summary(group_id):
    """Zwraca podsumowanie punktów dla obu semestrów danego roku szkolnego."""
    try:
        # Pobierz rok szkolny z parametru (domyślnie obecny rok)
        school_year = request.args.get('school_year_start', type=int, default=datetime.now(TZ).year)
    except ValueError:
        return jsonify({"error": "Nieprawidłowy rok szkolny"}), 400

    # Daty dla semestrów
    # Semestr 1: Wrzesień - Styczeń (następnego roku)
    s1_start = date(school_year, 9, 1)
    s1_end = date(school_year + 1, 1, 31)

    # Semestr 2: Luty - Sierpień
    s2_start = date(school_year + 1, 2, 1)
    s2_end = date(school_year + 1, 8, 31)

    results = {}

    try:
        with session_scope() as session:
            # Funkcja pomocnicza do liczenia punktów wewnątrz sesji
            def get_stats(start_date, end_date, semester_num):
                # 1. Punkty z sesji (suma bonuses_awarded z tabeli TUSSession)
                sess_points = session.query(func.sum(TUSSession.bonuses_awarded)).filter(
                    TUSSession.group_id == group_id,
                    TUSSession.session_date.between(start_date, end_date)
                ).scalar() or 0

                # 2. Punkty ogólne (Super Bonusy) - FILTROWANIE PO SEMESTRZE
                # Tutaj jest kluczowa zmiana: filtrujemy po kolumnie 'semester'
                gen_points = session.query(func.sum(TUSGeneralBonus.points)).filter(
                    TUSGeneralBonus.group_id == group_id,
                    TUSGeneralBonus.semester == semester_num  # <--- WAŻNE: Liczy tylko dla tego semestru
                ).scalar() or 0

                # 3. Cel (Target) dla tego semestru
                target = session.query(TUSGroupTarget).filter(
                    TUSGroupTarget.group_id == group_id,
                    TUSGroupTarget.school_year_start == school_year,
                    TUSGroupTarget.semester == semester_num
                ).first()

                total = int(sess_points) + int(gen_points)
                tgt_points = target.target_points if target else 0

                return {
                    'points_collected': total,
                    'target_points': tgt_points,
                    'points_remaining': max(0, tgt_points - total),
                    'reward': target.reward if target else None
                }

            # Zbieramy dane dla obu semestrów
            results['semester_1'] = get_stats(s1_start, s1_end, 1)
            results['semester_2'] = get_stats(s2_start, s2_end, 2)

            return jsonify({
                "school_year_start": school_year,
                "school_year_label": f"{school_year}/{school_year + 1}",
                **results
            })

    except Exception as e:
        print(f"Błąd w get_group_bonuses_summary: {e}")
        return jsonify({'error': str(e)}), 500


@app.post("/api/tus/member-bonuses")
@login_required
def add_member_bonus():
    data = request.get_json(silent=True) or {}
    try:
        session_id = int(data.get("session_id"))
        client_id = int(data.get("client_id"))
        points = int(data.get("points"))
    except (TypeError, ValueError):
        return jsonify({"error": "session_id, client_id, points (int) są wymagane"}), 400
    if points < 0:
        return jsonify({"error": "points >= 0"}), 400

    with engine.begin() as conn:
        # 1) sprawdź sesję i ustal group_id
        row = conn.execute(text("SELECT id, group_id FROM tus_sessions WHERE id=:sid"),
                           {"sid": session_id}).mappings().first()
        if not row:
            return jsonify({"error": "Sesja nie istnieje"}), 404
        gid = row["group_id"]

        # 2) sprawdź członkostwo klienta w grupie
        member = conn.execute(text("""
                SELECT 1 FROM tus_group_members
                WHERE group_id=:gid AND client_id=:cid
            """), {"gid": gid, "cid": client_id}).scalar()
        if not member:
            return jsonify({"error": "Klient nie należy do tej grupy"}), 400

        # 3) wstaw bonus
        new_id = conn.execute(text("""
                INSERT INTO tus_member_bonuses (session_id, client_id, points)
                VALUES (:sid, :cid, :pts)
                RETURNING id
            """), {"sid": session_id, "cid": client_id, "pts": points}).scalar_one()

    return jsonify({"id": new_id, "ok": True}), 201


def _half_bounds(year: int, half: int):
    if half == 1:
        a = datetime(year, 1, 1, tzinfo=TZ);
        b = datetime(year, 7, 1, tzinfo=TZ)
    else:
        a = datetime(year, 7, 1, tzinfo=TZ);
        b = datetime(year + 1, 1, 1, tzinfo=TZ)
    return a, b


# ==========================================
# 1. TEMATY (Poprawiona obsługa duplikatów)
# ==========================================
@app.route('/api/tus/topics', methods=['GET', 'POST'])
def handle_topics():
    try:
        # GET: Pobierz listę
        if request.method == 'GET':
            with session_scope() as session:
                topics = session.query(TUSTopic).order_by(TUSTopic.title).all()
                return jsonify([{'id': t.id, 'title': t.title} for t in topics]), 200

        # POST: Dodaj temat (Get-or-Create)
        if request.method == 'POST':
            data = request.get_json()
            title = data.get('title', '').strip()
            if not title:
                return jsonify({'error': 'Tytuł jest wymagany'}), 400

            with session_scope() as session:
                # SPRAWDŹ CZY JUŻ ISTNIEJE (Case-insensitive)
                existing = session.query(TUSTopic).filter(func.lower(TUSTopic.title) == title.lower()).first()

                if existing:
                    # Jeśli istnieje, zwróć go zamiast rzucać błędem!
                    return jsonify({'message': 'Temat już istnieje', 'id': existing.id, 'title': existing.title}), 200

                # Jeśli nie istnieje, utwórz nowy
                new_topic = TUSTopic(title=title)
                session.add(new_topic)
                session.commit()
                return jsonify({'message': 'Utworzono temat', 'id': new_topic.id, 'title': new_topic.title}), 201

    except Exception as e:
        return jsonify({'error': str(e)}), 500


# CRUD dla tematów (prosty przykład)



@app.post("/api/tus/topics")
def create_tus_topic():
    data = request.get_json(silent=True) or {}

    with session_scope() as db_session:
        try:
            new_topic = TUSTopic(title=data["title"])
            db_session.add(new_topic)
            db_session.flush()  # To jest potrzebne, aby uzyskać ID przed końcem transakcji

            result = {"id": new_topic.id, "title": new_topic.title}
            return jsonify(result), 201

        except IntegrityError:
            # Rollback i close są obsługiwane automatycznie przez session_scope
            return jsonify({"error": "Topic with this title already exists"}), 409


@app.get("/api/tus/behaviors")
@login_required  # Blokada dla zalogowanych
def get_behaviors():
    try:
        # Pobieramy ID Twojej fundacji z sesji
        current_firma_id = session.get('firma_id', 1)
        
        # Używamy poprawnej nazwy: SessionLocal zamiast Session
        with SessionLocal() as s:
            rows = (
                s.query(TUSBehavior)
                .filter_by(active=True, firma_id=current_firma_id)
                .order_by(TUSBehavior.title)
                .all()
            )
            return jsonify([{"id": b.id, "title": b.title, "default_max_points": b.default_max_points} for b in rows]), 200
            
    except Exception as e:
        print(f"⚠️ Błąd w get_behaviors: {e}")
        # W razie awarii zwracamy pustą listę, żeby frontend się nie zawiesił
        return jsonify([]), 200


@app.post("/api/tus/behaviors")
@login_required
def create_behavior():
    data = request.get_json(silent=True) or {}
    title = (data.get("title") or "").strip()
    dmp = int(data.get("default_max_points") or 3)
    current_firma_id = session.get('firma_id', 1)
    
    if not title:
        return jsonify({"error": "Tytuł jest wymagany"}), 400
        
    with session_scope() as s: # ✅ Użyj swojego ujednoliconego managera sesji
        b = TUSBehavior(title=title, default_max_points=dmp, firma_id=current_firma_id)
        s.add(b)
        return jsonify({"id": b.id, "title": b.title}), 201


@app.delete("/api/tus/behaviors/<int:bid>")
def delete_behavior(bid):
    with session_scope() as s:
        b = s.query(TUSBehavior).filter_by(id=bid).first()
        if not b: return "", 204
        b.active = False
        return "", 204


@app.get("/api/tus/sessions/<int:sid>/behaviors")
def session_behaviors(sid):
    with engine.begin() as conn:
        q = text("""
              SELECT sb.id, sb.behavior_id, b.title, sb.max_points
              FROM tus_session_behaviors sb
              JOIN tus_behaviors b ON b.id=sb.behavior_id
              WHERE sb.session_id=:sid
              ORDER BY b.title
            """)
        rows = conn.execute(q, {"sid": sid}).mappings().all()
        return jsonify([dict(r) for r in rows])


@app.post("/api/tus/sessions/<int:sid>/behaviors")
def set_session_behaviors(sid):
    """
        Body: { behaviors: [ {behavior_id, max_points?}, ... ] }  # max 4
        """
    data = request.get_json(silent=True) or {}
    items = data.get("behaviors") or []
    if len(items) > 4:
        return jsonify({"error": "max 4 behaviors per session"}), 400
    with engine.begin() as conn:
        # wyczyść i wstaw
        conn.execute(text("DELETE FROM tus_session_behaviors WHERE session_id=:sid"), {"sid": sid})
        for it in items:
            bid = int(it["behavior_id"])
            mp = int(it.get("max_points", 3))
            conn.execute(text("""
                  INSERT INTO tus_session_behaviors(session_id, behavior_id, max_points)
                  VALUES (:sid, :bid, :mp)
                """), {"sid": sid, "bid": bid, "mp": mp})
    return jsonify({"ok": True}), 200


@app.get("/api/tus/sessions/<int:sid>/scores")
@login_required
def get_session_scores(sid):
    try:
        with engine.connect() as conn:  # Używamy connect() dla odczytu
            # 1. Pobierz ID grupy dla tej sesji
            # (Mappings().first() zwraca None jeśli nie ma wyniku, zamiast rzucać błąd)
            session_row = conn.execute(
                text("SELECT group_id FROM tus_sessions WHERE id=:sid"),
                {"sid": sid}
            ).mappings().first()

            if not session_row:
                return jsonify({"error": "Sesja nie istnieje"}), 404

            gid = session_row['group_id']

            # 2. Pobierz Zachowania (Behaviors)
            beh_rows = conn.execute(text("""
                  SELECT sb.behavior_id, b.title, sb.max_points
                  FROM tus_session_behaviors sb
                  JOIN tus_behaviors b ON b.id=sb.behavior_id
                  WHERE sb.session_id=:sid
                  ORDER BY b.title
                """), {"sid": sid}).mappings().all()

            behaviors = [dict(b) for b in beh_rows]

            # 3. Pobierz Uczestników (Members) z grupy
            mem_rows = conn.execute(text("""
                  SELECT c.id, c.full_name
                  FROM tus_groups g
                  JOIN tus_group_members gm ON gm.group_id=g.id
                  JOIN clients c ON c.id=gm.client_id
                  WHERE g.id=:gid
                  ORDER BY c.full_name
                """), {"gid": gid}).mappings().all()

            members = [dict(m) for m in mem_rows]

            # 4. Pobierz Punkty (Scores)
            sc_rows = conn.execute(text("""
                  SELECT client_id, behavior_id, points
                  FROM tus_session_member_scores
                  WHERE session_id=:sid
                """), {"sid": sid}).mappings().all()

            scores = {}
            for r in sc_rows:
                # Zabezpieczenie przed brakiem klucza
                cid = r['client_id']
                bid = r['behavior_id']
                if cid not in scores: scores[cid] = {}
                scores[cid][bid] = r['points']

            # 5. Pobierz Nagrody (Rewards) - ZABEZPIECZONE PRZED NULL
            rw_rows = conn.execute(text("""
                  SELECT client_id, awarded, note, points 
                  FROM tus_session_partial_rewards
                  WHERE session_id=:sid
                """), {"sid": sid}).mappings().all()

            rewards = {}
            for r in rw_rows:
                rewards[r["client_id"]] = {
                    "awarded": bool(r["awarded"]),  # Zamiana None/0/1 na False/True
                    "note": r["note"] if r["note"] else "",  # Zamiana None na pusty string
                    "points": int(r["points"] or 0)  # Zamiana None na 0
                }

            return jsonify({
                "behaviors": behaviors,
                "members": members,
                "scores": scores,
                "rewards": rewards
            })

    except Exception as e:
        # Ten blok wyświetli dokładną przyczynę błędu w terminalu (konsoli), gdzie uruchomiony jest Python
        print(f"❌ KRYTYCZNY BŁĄD w get_session_scores: {str(e)}")
        import traceback
        traceback.print_exc()
        return jsonify({"error": f"Błąd serwera: {str(e)}"}), 500


@app.post("/api/tus/sessions/<int:sid>/scores")
def save_session_scores(sid):
    """
    Zapisuje punktację sesji.
    Wersja AUTO-NAPRAWCZA: Resetuje liczniki ID przed zapisem.
    """
    data = request.get_json(silent=True) or {}
    items = data.get("scores") or []

    try:
        with engine.begin() as conn:
            # === KROK 0: AUTO-NAPRAWA LICZNIKÓW (Fix Sequence) ===
            # To rozwiązuje Twój błąd "UniqueViolation" raz na zawsze
            conn.execute(text("""
                SELECT setval(pg_get_serial_sequence('tus_session_member_scores', 'id'), COALESCE(max(id), 0) + 1, false)
                FROM tus_session_member_scores;
            """))
            conn.execute(text("""
                SELECT setval(pg_get_serial_sequence('tus_session_partial_rewards', 'id'), COALESCE(max(id), 0) + 1, false)
                FROM tus_session_partial_rewards;
            """))

            # === KROK 1: Pobranie limitów (walidacja) ===
            limits = {
                r["behavior_id"]: r["max_points"]
                for r in conn.execute(
                    text("SELECT behavior_id, max_points FROM tus_session_behaviors WHERE session_id=:sid"),
                    {"sid": sid}
                ).mappings().all()
            }

            # === KROK 2: Wyczyszczenie starych danych dla TEJ sesji ===
            conn.execute(text("DELETE FROM tus_session_member_scores WHERE session_id=:sid"), {"sid": sid})
            conn.execute(text("DELETE FROM tus_session_partial_rewards WHERE session_id=:sid"), {"sid": sid})

            # === KROK 3: Wstawienie nowych danych ===
            for row in items:
                cid = int(row["client_id"])

                # A. Punkty za zachowania
                for it in (row.get("items") or []):
                    bid = int(it["behavior_id"])
                    pts = int(it.get("points", 0))

                    if bid not in limits: continue  # Pomijamy usunięte zachowania

                    # Walidacja zakresu
                    max_pts = limits[bid]
                    if pts < 0: pts = 0
                    if pts > max_pts: pts = max_pts

                    conn.execute(text("""
                        INSERT INTO tus_session_member_scores (session_id, client_id, behavior_id, points)
                        VALUES (:sid, :cid, :bid, :pts)
                    """), {"sid": sid, "cid": cid, "bid": bid, "pts": pts})

                # B. Nagroda cząstkowa
                pr = row.get("partial_reward") or {}
                awarded = bool(pr.get("awarded"))
                points = int(pr.get("points", 0))
                note = pr.get("note", "") or ""

                if awarded or points > 0 or note:
                    conn.execute(text("""
                        INSERT INTO tus_session_partial_rewards (session_id, client_id, awarded, note, points, awarded_at)
                        VALUES (:sid, :cid, :aw, :note, :pts, CASE WHEN :aw THEN NOW() ELSE NULL END)
                    """), {
                        "sid": sid, "cid": cid, "aw": awarded, "note": note, "pts": points
                    })

        return jsonify({"ok": True}), 200

    except Exception as e:
        print(f"Błąd zapisu: {e}")
        return jsonify({"error": str(e)}), 500


# def _half_bounds(year:int, half:int):
#    if half == 1:
#        a = datetime(year,1,1,tzinfo=TZ); b = datetime(year,7,1,tzinfo=TZ)
#    else:
#        a = datetime(year,7,1,tzinfo=TZ); b = datetime(year+1,1,1,tzinfo=TZ)
#    return a,b

@app.get("/api/gaps/day")
def gaps_day():
    """
        Zwraca listy aktywnych klientów/terapeutów/kierowców,
        którzy NIE mają żadnego slotu w danym dniu.
        Param: ?date=YYYY-MM-DD (domyślnie dzisiaj w Europe/Warsaw)
        """
    qd = (request.args.get("date") or "").strip()
    if not qd:
        d = datetime.now(TZ).date()
    else:
        try:
            d = datetime.fromisoformat(qd).date()
        except ValueError:
            return jsonify({"error": "Invalid date. Use YYYY-MM-DD"}), 400

    sql_clients = """
          SELECT c.id, c.full_name
          FROM clients c
          LEFT JOIN schedule_slots ss
            ON ss.client_id = c.id
           AND ss.starts_at::date = :d
          WHERE c.active = true
            AND ss.id IS NULL
          ORDER BY c.full_name;
        """

    # terapeuta: brak żadnej TERAPII tego dnia
    sql_therapists = """
          SELECT t.id, t.full_name
          FROM therapists t
          LEFT JOIN schedule_slots ss
            ON ss.therapist_id = t.id
           AND ss.kind = 'therapy'
           AND ss.starts_at::date = :d
          WHERE t.active = true
            AND ss.id IS NULL
          ORDER BY t.full_name;
        """

    # kierowca: brak żadnego kursu (pickup/dropoff) tego dnia
    sql_drivers = """
          SELECT d.id, d.full_name
          FROM drivers d
          LEFT JOIN schedule_slots ss
            ON ss.driver_id = d.id
           AND ss.kind IN ('pickup','dropoff')
           AND ss.starts_at::date = :d
          WHERE d.active = true
            AND ss.id IS NULL
          ORDER BY d.full_name;
        """

    with engine.begin() as conn:
        clients = [dict(r) for r in conn.execute(text(sql_clients), {"d": d}).mappings().all()]
        therapists = [dict(r) for r in conn.execute(text(sql_therapists), {"d": d}).mappings().all()]
        drivers = [dict(r) for r in conn.execute(text(sql_drivers), {"d": d}).mappings().all()]

    return jsonify({
        "date": d.isoformat(),
        "clients": clients,
        "therapists": therapists,
        "drivers": drivers,
        "counts": {
            "clients": len(clients),
            "therapists": len(therapists),
            "drivers": len(drivers),
        }
    }), 200


@app.get("/api/gaps/month")
def gaps_month():
    """
        Zwraca aktywnych klientów / terapeutów / kierowców,
        którzy w danym miesiącu NIE mają żadnego slotu.
        Dodatkowo zwraca informacje o nieobecnościach.
        """
    mk = (request.args.get("month") or "").strip()
    if not mk:
        mk = datetime.now(TZ).strftime("%Y-%m")

    # Klient: brak JAKIEGOKOLWIEK slotu w miesiącu
    sql_clients = """
          SELECT c.id, c.full_name
          FROM clients c
          WHERE c.active = true
            AND NOT EXISTS (
              SELECT 1 FROM schedule_slots ss
              WHERE ss.client_id = c.id
                AND ss.starts_at IS NOT NULL
                AND to_char(ss.starts_at AT TIME ZONE 'Europe/Warsaw','YYYY-MM') = :mk
            )
          ORDER BY c.full_name;
        """

    # Terapeuta: brak TERAPII w miesiącu
    sql_therapists = """
          SELECT t.id, t.full_name
          FROM therapists t
          WHERE t.active = true
            AND NOT EXISTS (
              SELECT 1 FROM schedule_slots ss
              WHERE ss.therapist_id = t.id
                AND ss.kind = 'therapy'
                AND ss.starts_at IS NOT NULL
                AND to_char(ss.starts_at AT TIME ZONE 'Europe/Warsaw','YYYY-MM') = :mk
            )
          ORDER BY t.full_name;
        """

    # Kierowca: brak kursów (pickup/dropoff) w miesiącu
    sql_drivers = """
          SELECT d.id, d.full_name
          FROM drivers d
          WHERE d.active = true
            AND NOT EXISTS (
              SELECT 1 FROM schedule_slots ss
              WHERE ss.driver_id = d.id
                AND ss.kind IN ('pickup','dropoff')
                AND ss.starts_at IS NOT NULL
                AND to_char(ss.starts_at AT TIME ZONE 'Europe/Warsaw','YYYY-MM') = :mk
            )
          ORDER BY d.full_name;
        """

    # NOWOŚĆ: Pobieranie nieobecności
    sql_absences = text("""
            SELECT person_type, person_id, status 
            FROM absences
            WHERE to_char(start_date, 'YYYY-MM') <= :mk AND to_char(end_date, 'YYYY-MM') >= :mk
        """)

    with engine.begin() as conn:
        clients = [dict(r) for r in conn.execute(text(sql_clients), {"mk": mk}).mappings().all()]
        therapists = [dict(r) for r in conn.execute(text(sql_therapists), {"mk": mk}).mappings().all()]
        drivers = [dict(r) for r in conn.execute(text(sql_drivers), {"mk": mk}).mappings().all()]
        absences_rows = conn.execute(sql_absences, {"mk": mk}).mappings().all()

    # Przetwórz nieobecności w słownik dla łatwego dostępu
    absences_map = {}
    for ab in absences_rows:
        key = (ab['person_type'], ab['person_id'])
        absences_map[key] = ab['status']

    # Dodaj informacje o nieobecnościach do wyników
    for t in therapists:
        if ('therapist', t['id']) in absences_map:
            t['absence_status'] = absences_map[('therapist', t['id'])]

    for d in drivers:
        if ('driver', d['id']) in absences_map:
            d['absence_status'] = absences_map[('driver', d['id'])]

    return jsonify({
        "month": mk,
        "clients": clients,
        "therapists": therapists,
        "drivers": drivers,
        "counts": {
            "clients": len(clients),
            "therapists": len(therapists),
            "drivers": len(drivers),
        }
    }), 200


@app.route('/api/therapists/summary', methods=['GET'])
@login_required
def get_therapists_summary():
    """
    Zwraca zestawienie godzin pracy (minut) dla WSZYSTKICH terapeutów
    w podanym miesiącu (parametr month=YYYY-MM).
    """
    month_key = request.args.get("month")

    if not month_key:
        return jsonify({"error": "Parametr 'month' (YYYY-MM) jest wymagany."}), 400

    # Sprawdzanie poprawności formatu RRRR-MM (jak wcześniej)
    try:
        year, month = map(int, month_key.split('-'))
        if year < 2000 or month < 1 or month > 12:
            raise ValueError
    except ValueError:
        return jsonify({"error": "Nieprawidłowy format miesiąca. Użyj formatu YYYY-MM."}), 400

    try:
        with engine.begin() as conn:
            # KLUCZOWE ZAPYTANIE: Sumuje minuty ze slotów indywidualnych i TUS dla każdego terapeuty
            sql = text("""
                WITH AllSessions AS (
                    -- 1. Sesje indywidualne (schedule_slots)
                    SELECT 
                        ss.therapist_id,
                        EXTRACT(EPOCH FROM (ss.ends_at - ss.starts_at)) / 60 AS duration_minutes
                    FROM schedule_slots ss
                    WHERE ss.therapist_id IS NOT NULL
                      AND ss.kind = 'therapy'
                      AND ss.status != 'cancelled'
                      AND EXTRACT(YEAR FROM ss.starts_at) = :year
                      AND EXTRACT(MONTH FROM ss.starts_at) = :month
                ),
                TusSessions AS (
                    -- 2. Sesje TUS (dla terapeuty i asystenta, 60 minut każda)
                    SELECT 
                        g.therapist_id AS therapist_id,
                        60 AS duration_minutes
                    FROM tus_sessions s
                    JOIN tus_groups g ON s.group_id = g.id
                    WHERE EXTRACT(YEAR FROM s.session_date) = :year
                      AND EXTRACT(MONTH FROM s.session_date) = :month

                    UNION ALL

                    SELECT 
                        g.assistant_therapist_id AS therapist_id,
                        60 AS duration_minutes
                    FROM tus_sessions s
                    JOIN tus_groups g ON s.group_id = g.id
                    WHERE g.assistant_therapist_id IS NOT NULL
                      AND EXTRACT(YEAR FROM s.session_date) = :year
                      AND EXTRACT(MONTH FROM s.session_date) = :month
                ),
                CombinedSessions AS (
                    SELECT therapist_id, duration_minutes FROM AllSessions
                    UNION ALL
                    SELECT therapist_id, duration_minutes FROM TusSessions
                )

                -- Sumowanie wszystkich minut
                SELECT 
                    t.id AS therapist_id, 
                    t.full_name,
                    COALESCE(SUM(cs.duration_minutes), 0) AS total_minutes
                FROM therapists t
                LEFT JOIN CombinedSessions cs ON cs.therapist_id = t.id
                WHERE t.active = TRUE
                GROUP BY t.id, t.full_name
                ORDER BY t.full_name;
            """)

            params = {"year": year, "month": month}
            rows = conn.execute(sql, params).mappings().all()

            results = []
            for r in rows:
                results.append({
                    "therapist_id": r['therapist_id'],
                    "full_name": r['full_name'],
                    "total_minutes": int(r['total_minutes'] or 0)
                })

            return jsonify(results), 200

    except Exception as e:

        log_activity(f"Błąd generowania zestawienia terapeutów: {e}")
        import traceback
        traceback.print_exc()
        return jsonify({"error": f"Błąd serwera podczas zestawienia: {str(e)}"}), 500


@app.route('/api/therapists/<int:therapist_id>/monthly-summary', methods=['GET'])
@login_required
def get_therapist_detailed_summary(therapist_id):
    """
    Zwraca szczegółowe zestawienie godzin (minut) dla JEDNEGO terapeuty
    w podanym miesiącu (parametr month=YYYY-MM).
    """
    month_key = request.args.get("month")

    if not month_key:
        return jsonify({"error": "Parametr 'month' (YYYY-MM) jest wymagany."}), 400

    try:
        year, month = map(int, month_key.split('-'))
    except ValueError:
        return jsonify({"error": "Nieprawidłowy format miesiąca. Użyj formatu YYYY-MM."}), 400

    try:
        with engine.begin() as conn:
            # 1. INDYWIDUALNE (Zabezpieczone COALESCE i AT TIME ZONE)
            sql_individual = text("""
                SELECT 
                    COALESCE(SUM(EXTRACT(EPOCH FROM (ss.ends_at - ss.starts_at)) / 60), 0)
                FROM schedule_slots ss
                WHERE ss.therapist_id = :tid
                  AND ss.kind = 'therapy'

                  -- Bezpieczne sprawdzenie statusu (traktuje NULL jako 'planned')
                  AND COALESCE(ss.status, 'planned') != 'cancelled' 

                  -- Wymuszenie strefy czasowej polskiej przy wyciąganiu miesiąca
                  AND EXTRACT(YEAR FROM ss.starts_at AT TIME ZONE 'Europe/Warsaw') = :year
                  AND EXTRACT(MONTH FROM ss.starts_at AT TIME ZONE 'Europe/Warsaw') = :month
            """)

            individual_minutes_raw = conn.execute(sql_individual, {
                "tid": therapist_id, "year": year, "month": month
            }).scalar_one()

            # 2. TUS (Zabezpieczone)
            sql_tus = text("""
                SELECT 
                    COALESCE(COUNT(s.id), 0) * 60
                FROM tus_sessions s
                JOIN tus_groups g ON s.group_id = g.id
                WHERE (g.therapist_id = :tid OR g.assistant_therapist_id = :tid)
                  AND EXTRACT(YEAR FROM s.session_date) = :year
                  AND EXTRACT(MONTH FROM s.session_date) = :month
            """)

            tus_minutes_raw = conn.execute(sql_tus, {
                "tid": therapist_id, "year": year, "month": month
            }).scalar_one()

            # 3. Jawna konwersja na liczby całkowite (INT) i obsługa None
            # (Choć COALESCE(..., 0) w SQL powinno to robić, ta linia jest dodatkowym zabezpieczeniem)
            individual_minutes = int(individual_minutes_raw or 0)
            tus_minutes = int(tus_minutes_raw or 0)

            # 4. Pobranie danych terapeuty
            therapist_data = conn.execute(text("SELECT full_name FROM therapists WHERE id = :tid"),
                                          {"tid": therapist_id}).mappings().first()

            if not therapist_data:
                return jsonify({"error": "Terapeuta nie znaleziony."}), 404

            total_minutes = individual_minutes + tus_minutes

            # 5. Zestawienie
            summary = {
                "therapist_id": therapist_id,
                "full_name": therapist_data['full_name'],
                "month_key": month_key,
                "total_minutes": total_minutes,
                "individual_minutes": individual_minutes,
                "tus_minutes": tus_minutes
            }

            return jsonify(summary), 200

    except Exception as e:
        log_activity(f"Błąd generowania szczegółowego zestawienia: {e}")
        return jsonify({"error": f"Błąd serwera: {str(e)}"}), 500


# W pliku app.py
@app.get("/api/client/<int:cid>/packages")
@login_required
def client_packages(cid):
    mk = request.args.get("month")

    sql = text("""
        WITH all_events AS (
            -- 1. ZAJĘCIA INDYWIDUALNE ORAZ ZAIMPORTOWANE GRUPOWE (z tabeli schedule_slots)
            SELECT
                CASE 
                    WHEN ss.group_tus_id IS NOT NULL THEN 'tus' 
                    ELSE 'individual' 
                END as type, 
                COALESCE(eg.id::text, 'no-group') AS group_id, 
                COALESCE(eg.label, 'Wizyta indywidualna') AS label, 
                NULL::text as group_name,
                ss.id AS slot_id,
                ss.kind::text AS kind,  
                ss.starts_at, 
                ss.ends_at, 
                ss.status, 
                ss.therapist_id, 
                t.full_name AS therapist_name,
                ss.driver_id, 
                d.full_name AS driver_name, 
                ss.place_from, 
                ss.place_to, 
                ss.distance_km,
                NULL::json AS members -- <--- DODANE (Puste dla zajęć indywidualnych)
            FROM schedule_slots ss
            LEFT JOIN event_groups eg ON eg.id::text = ss.group_id::text  
            LEFT JOIN therapists t ON t.id = ss.therapist_id
            LEFT JOIN drivers d ON d.id = ss.driver_id
            WHERE ss.client_id = :cid
              AND ss.status != 'cancelled'

            UNION ALL

            -- 2. OFICJALNE ZAJĘCIA Z MODUŁU TUS (z tabeli tus_sessions)
            SELECT
                'tus' as type, 
                g.id::text AS group_id, 
                COALESCE(tt.title, g.name) AS label,
                g.name::text as group_name,
                s.id AS slot_id, 
                'tus' AS kind, 
                (s.session_date::timestamp + COALESCE(s.session_time, '00:00:00')::time) AT TIME ZONE 'Europe/Warsaw' AS starts_at,
                (s.session_date::timestamp + COALESCE(s.session_time, '00:00:00')::time + INTERVAL '60 minutes') AT TIME ZONE 'Europe/Warsaw' AS ends_at,
                'planned' as status, 
                g.therapist_id, 
                th.full_name AS therapist_name,
                NULL::integer AS driver_id, 
                NULL::text AS driver_name, 
                'Poradnia' AS place_from, 
                'Poradnia' AS place_to, 
                NULL::float as distance_km,

                -- <--- DODANE: Pobieranie imion i nazwisk członków grupy TUS --->
                (SELECT json_agg(json_build_object('id', c.id, 'name', c.full_name))
                 FROM tus_group_members gm2
                 JOIN clients c ON c.id = gm2.client_id
                 WHERE gm2.group_id = g.id
                   AND gm2.is_active = true
                ) AS members

            FROM tus_sessions s
            JOIN tus_groups g ON s.group_id = g.id
            JOIN tus_group_members gm ON gm.group_id = g.id
            LEFT JOIN therapists th ON g.therapist_id = th.id
            LEFT JOIN tus_topics tt ON s.topic_id = tt.id
            WHERE gm.client_id = :cid
              AND gm.is_active = true
        )
        SELECT * FROM all_events
        WHERE (:mk IS NULL OR to_char(starts_at AT TIME ZONE 'Europe/Warsaw', 'YYYY-MM') = :mk)
        ORDER BY starts_at;
    """)

    try:
        with engine.begin() as conn:
            rows = conn.execute(sql, {"cid": cid, "mk": mk}).mappings().all()
            results = []
            for r in rows:
                row_dict = dict(r)

                if starts_at_aware := r.get('starts_at'):
                    if starts_at_aware.tzinfo is None:
                        starts_at_aware = starts_at_aware.replace(tzinfo=TZ)
                    row_dict['starts_at'] = starts_at_aware.astimezone(TZ).isoformat()

                if ends_at_aware := r.get('ends_at'):
                    if ends_at_aware.tzinfo is None:
                        ends_at_aware = ends_at_aware.replace(tzinfo=TZ)
                    row_dict['ends_at'] = ends_at_aware.astimezone(TZ).isoformat()

                results.append(row_dict)
            return jsonify(results)

    except Exception as e:
        print(f"Błąd w client_packages: {e}")
        import traceback
        traceback.print_exc()
        return jsonify({"error": str(e)}), 500

# === DRIVER SCHEDULE (kursy kierowcy z klientami) ===



# BACKEND (Flask)
@app.patch("/api/slots/<int:sid>")
def update_slot(sid):
    data = request.get_json(silent=True) or {}
    fields = []
    params = {"sid": sid}
    if "status" in data:
        fields.append("status=:status")
        params["status"] = data["status"]
    if "starts_at" in data:
        fields.append("starts_at=:starts_at")
        params["starts_at"] = datetime.fromisoformat(data["starts_at"]).replace(tzinfo=TZ)
    if "ends_at" in data:
        fields.append("ends_at=:ends_at")
        params["ends_at"] = datetime.fromisoformat(data["ends_at"]).replace(tzinfo=TZ)
    if not fields:
        return jsonify({"error": "No fields"}), 400
    sql = f"UPDATE schedule_slots SET {', '.join(fields)} WHERE id=:sid RETURNING id;"
    with engine.begin() as conn:
        row = conn.execute(text(sql), params).mappings().first()
        if not row: return jsonify({"error": "Not found"}), 404
        return jsonify({"ok": True, "id": row["id"]}), 200


# W app.py

@app.route('/api/slots/<int:slot_id>/status', methods=['PATCH'])
# Prawdopodobnie powinien być tu @login_required
def update_slot_status(slot_id):
    """Aktualizuje status pojedynczego slotu w schedule_slots."""
    data = request.get_json()
    if not data:
        return jsonify({"error": "Brak danych JSON"}), 400

    new_status = data.get('status')
    if not new_status:
        return jsonify({"error": "Brak parametru 'status'"}), 400

    # Walidacja statusu
    valid_statuses = ['planned', 'confirmed', 'done', 'cancelled']
    if new_status not in valid_statuses:
        return jsonify({"error": f"Nieprawidłowy status. Dozwolone: {', '.join(valid_statuses)}"}), 400

    try:
        with engine.begin() as conn:
            # 1. Sprawdzamy, czy slot istnieje ORAZ czy jest to slot terapii indywidualnej
            result = conn.execute(
                text("SELECT id FROM schedule_slots WHERE id = :id AND kind = 'therapy'"),
                {"id": slot_id}
            )
            slot_exists = result.scalar()

            if not slot_exists:
                # Zwracamy 404 tylko, jeśli to nie jest slot terapii.
                # Jeśli to slot TUS, to po prostu go ignorujemy w tej logice.
                # W tym wypadku lepiej zwrócić 404, jak pierwotnie Pan zakładał.
                return jsonify(
                    {"error": "Slot nie znaleziony w schedule_slots (lub nie jest terapią indywidualną)."}), 404

            # 2. Aktualizuj status
            conn.execute(
                text("UPDATE schedule_slots SET status = :status WHERE id = :id"),
                {"status": new_status, "id": slot_id}
            )

            return jsonify({
                "status": "ok",
                "slot_id": slot_id,
                "new_status": new_status,
                "message": "Status zaktualizowany"
            })

    except Exception as e:
        log_activity(f"BŁĄD w update_slot_status: {e}")
        import traceback
        traceback.print_exc()
        return jsonify({"error": f"Wewnętrzny błąd serwera: {str(e)}"}), 500


@app.get("/api/tus/groups-summary")
@login_required  # Wymagamy zalogowania dla bezpieczeństwa danych
def get_tus_groups_summary():
    """Zwraca podsumowanie dla kart grup z podziałem na semestry z blokadą Multi-tenant."""
    try:
        # Pobranie firma_id z sesji (fallback na 1)
        current_firma_id = session.get('firma_id', 1)

        with SessionLocal() as session_db:
            # Ustalamy bieżący rok szkolny
            now = datetime.now(TZ).date()
            current_school_year = now.year if now.month >= 9 else now.year - 1

            # Daty graniczne dla semestrów
            s1_start, s1_end = get_semester_dates(current_school_year, 1)
            s2_start, s2_end = get_semester_dates(current_school_year, 2)

            # 1. Podzapytania z filtrem firma_id
            sess_s1 = (
                session_db.query(TUSSession.group_id, func.sum(TUSSession.bonuses_awarded).label('pts'))
                .filter(TUSSession.session_date.between(s1_start, s1_end), TUSSession.firma_id == current_firma_id)
                .group_by(TUSSession.group_id).subquery()
            )
            sess_s2 = (
                session_db.query(TUSSession.group_id, func.sum(TUSSession.bonuses_awarded).label('pts'))
                .filter(TUSSession.session_date.between(s2_start, s2_end), TUSSession.firma_id == current_firma_id)
                .group_by(TUSSession.group_id).subquery()
            )

            gen_s1 = (
                session_db.query(TUSGeneralBonus.group_id, func.sum(TUSGeneralBonus.points).label('pts'))
                .filter(TUSGeneralBonus.semester == 1, TUSGeneralBonus.firma_id == current_firma_id)
                .group_by(TUSGeneralBonus.group_id).subquery()
            )
            gen_s2 = (
                session_db.query(TUSGeneralBonus.group_id, func.sum(TUSGeneralBonus.points).label('pts'))
                .filter(TUSGeneralBonus.semester == 2, TUSGeneralBonus.firma_id == current_firma_id)
                .group_by(TUSGeneralBonus.group_id).subquery()
            )

            target_s1 = (
                session_db.query(TUSGroupTarget.group_id, TUSGroupTarget.target_points.label('target'))
                .filter(TUSGroupTarget.school_year_start == current_school_year, TUSGroupTarget.semester == 1, TUSGroupTarget.firma_id == current_firma_id)
                .subquery()
            )
            target_s2 = (
                session_db.query(TUSGroupTarget.group_id, TUSGroupTarget.target_points.label('target'))
                .filter(TUSGroupTarget.school_year_start == current_school_year, TUSGroupTarget.semester == 2, TUSGroupTarget.firma_id == current_firma_id)
                .subquery()
            )

            last_topic_subq = (
                select(TUSSession.group_id, TUSTopic.title.label("last_topic_title"))
                .join(TUSTopic, TUSSession.topic_id == TUSTopic.id)
                .filter(TUSSession.firma_id == current_firma_id)
                .order_by(TUSSession.group_id, TUSSession.session_date.desc(), TUSSession.session_time.desc())
                .distinct(TUSSession.group_id).subquery()
            )

            # GŁÓWNE ZAPYTANIE - Dodany krytyczny filtr .filter(TUSGroup.firma_id == current_firma_id)
            groups = session_db.query(TUSGroup).options(
                joinedload(TUSGroup.therapist),
                joinedload(TUSGroup.member_associations).joinedload(TUSGroupMember.client)
            ).filter(TUSGroup.firma_id == current_firma_id).order_by(TUSGroup.name).all()

            def get_dict(subq):
                return {row[0]: row[1] or 0 for row in session_db.query(subq).all()}

            d_sess_s1 = get_dict(sess_s1)
            d_sess_s2 = get_dict(sess_s2)
            d_gen_s1 = get_dict(gen_s1)
            d_gen_s2 = get_dict(gen_s2)
            d_target_s1 = get_dict(target_s1)
            d_target_s2 = get_dict(target_s2)
            d_topics = {row[0]: row[1] for row in session_db.query(last_topic_subq).all()}

            result = []
            for g in groups:
                s1_collected = d_sess_s1.get(g.id, 0) + d_gen_s1.get(g.id, 0)
                s1_target = d_target_s1.get(g.id, 0)
                s2_collected = d_sess_s2.get(g.id, 0) + d_gen_s2.get(g.id, 0)
                s2_target = d_target_s2.get(g.id, 0)

                result.append({
                    "id": g.id,
                    "name": g.name,
                    "therapist_name": g.therapist.full_name if g.therapist else "Brak",
                    "member_count": len(g.members),
                    "last_topic": d_topics.get(g.id, "Brak tematów"),
                    "s1_collected": s1_collected,
                    "s1_target": s1_target,
                    "s1_percent": min(100, int((s1_collected / s1_target) * 100)) if s1_target > 0 else 0,
                    "s2_collected": s2_collected,
                    "s2_target": s2_target,
                    "s2_percent": min(100, int((s2_collected / s2_target) * 100)) if s2_target > 0 else 0,
                })

            return jsonify(result), 200

    except Exception as e:
        print(f"⚠️ KRYTYCZNY BŁĄD w get_tus_groups_summary: {e}")
        import traceback
        traceback.print_exc()
        return jsonify([]), 200


@app.get("/api/tus/groups/<int:group_id>/topic-history")
def get_group_topic_history(group_id: int):
    with SessionLocal() as session:
        # Krok 1: Znajdź ID aktualnych członków grupy
        current_member_ids = session.execute(
            select(TUSGroupMember.client_id).where(TUSGroupMember.group_id == group_id)
        ).scalars().all()

        if not current_member_ids:
            return jsonify({})

        # Krok 2: Pobierz PEŁNĄ historię dla tych członków ze wszystkich grup
        history_query = (
            select(
                TUSGroupMember.client_id,
                Client.full_name,
                TUSTopic.title,
                TUSSession.session_date,
                TUSGroup.name
            )
            .distinct()
            .join(Client, Client.id == TUSGroupMember.client_id)
            .join(TUSGroup, TUSGroup.id == TUSGroupMember.group_id)
            .join(TUSSession, TUSSession.group_id == TUSGroup.id)
            .join(TUSTopic, TUSTopic.id == TUSSession.topic_id)
            .where(TUSGroupMember.client_id.in_(current_member_ids))
            .order_by(Client.full_name, TUSSession.session_date.desc())
        )

        history_results = session.execute(history_query).all()

        # Krok 3: Przetwarzanie wyników (bez zmian)
        history_by_client = {}
        for row in history_results:
            client_id, client_name, topic_title, session_date, group_name = row
            if client_id not in history_by_client:
                history_by_client[client_id] = {
                    "client_name": client_name,
                    "history": []
                }
            history_by_client[client_id]["history"].append({
                "topic": topic_title,
                "date": session_date.isoformat(),
                "group_name": group_name
            })

        return jsonify(history_by_client)


# Zmieniono URL z /clients/ na /client/ (liczba pojedyncza), aby pasował do panel.js
@app.route('/api/client/<int:client_id>/history', methods=['GET'])
@app.route('/api/clients/<int:client_id>/history', methods=['GET'])
def get_client_history(client_id):
    try:
        with engine.connect() as conn:  # Używamy connect() zamiast begin() dla odczytu
            # 1. Spotkania indywidualne
            # DODANO: ss.therapist_id (Kluczowe dla AI!)
            individual_sql = text('''
                    SELECT 
                        ss.id as slot_id,
                        ss.therapist_id, 
                        ss.starts_at,
                        ss.ends_at,
                        ss.status,
                        th.full_name as therapist_name,
                        eg.label as topic,
                        ss.place_to as place,
                        EXTRACT(EPOCH FROM (ss.ends_at - ss.starts_at))/60 as duration_minutes
                    FROM schedule_slots ss
                    LEFT JOIN therapists th ON th.id = ss.therapist_id
                    LEFT JOIN event_groups eg ON eg.id = ss.group_id
                    WHERE ss.client_id = :cid
                        AND ss.kind = 'therapy'
                        AND ss.status != 'cancelled'
                    ORDER BY ss.starts_at DESC
                ''')

            individual_rows = conn.execute(individual_sql, {"cid": client_id}).mappings().all()

            # 2. Notatki (Bez zmian, działa dobrze)
            notes_sql = text('''
                    SELECT DISTINCT ON (DATE(created_at))
                        id, content, created_at, category
                    FROM client_notes
                    WHERE client_id = :cid AND category = 'session'
                    ORDER BY DATE(created_at) DESC, created_at DESC
                ''')

            notes_rows = conn.execute(notes_sql, {"cid": client_id}).mappings().all()

            notes_map = {row['created_at'].date(): row['content'] for row in notes_rows}
            note_ids_map = {row['created_at'].date(): row['id'] for row in notes_rows}

            # 3. Spotkania TUS (Bez zmian)
                        # 3. Spotkania TUS
                        # 3. Spotkania TUS
            tus_sql = text('''
                    SELECT 
                        ts.session_date,
                        ts.session_time,
                        tt.title as topic_title,
                        tg.name as group_name
                    FROM tus_sessions ts
                    JOIN tus_groups tg ON tg.id = ts.group_id
                    JOIN tus_group_members tgm ON tgm.group_id = tg.id
                    LEFT JOIN tus_topics tt ON tt.id = ts.topic_id
                    WHERE tgm.client_id = :cid
                      -- KLUCZOWY FILTR: Obejmuje historię i obecne grupy
                      AND (tgm.join_date IS NULL OR ts.session_date >= tgm.join_date)
                      AND (tgm.leave_date IS NULL OR ts.session_date <= tgm.leave_date)
                    ORDER BY ts.session_date DESC
                ''')

            tus_rows = conn.execute(tus_sql, {"cid": client_id}).mappings().all()

            # 4. Formatowanie
            history = {
                "individual": [
                    {
                        "date": row['starts_at'].isoformat() if row['starts_at'] else None,
                        "status": row['status'] or "unknown",
                        "therapist_id": row['therapist_id'],  # WAŻNE DLA AI
                        "therapist": row['therapist_name'] or "Nieznany",
                        "topic": row['topic'] or "Bez tematu",
                        "notes": notes_map.get(row['starts_at'].date(), "") if row['starts_at'] else "",
                        "note_id": note_ids_map.get(row['starts_at'].date()) if row['starts_at'] else None,
                        "place": row['place'] or "",
                        "duration": int(row['duration_minutes']) if row['duration_minutes'] else 60,
                    } for row in individual_rows
                ],
                "tus_group": [
                    {
                        "date": row['session_date'].isoformat() if row['session_date'] else None,
                        "time": row['session_time'].strftime('%H:%M') if row['session_time'] else None,
                        "topic": row['topic_title'] or "Brak tematu",
                        "group": row['group_name'] or "Nieznana grupa"
                    } for row in tus_rows
                ]
            }

            return jsonify(history), 200

    except Exception as e:
        log_activity(f"❌ BŁĄD w get_client_history: {str(e)}")
        return jsonify({"error": str(e)}), 500


@app.get("/api/tus/schedule")
def get_tus_schedule():
    """
    Zwraca wszystkie sesje TUS w danym miesiącu.
    NOWOŚĆ: Zwraca każdą sesję RAZ i listę członków zagnieżdżoną jako JSON.
    """
    month_key = request.args.get("month")
    if not month_key:
        return jsonify({"error": "Parametr 'month' jest wymagany."}), 400

    sql = text("""
        SELECT
            s.id AS session_id,
            s.session_date,
            s.session_time,
            g.id AS group_id,
            g.name AS group_name,
            COALESCE(t.title, 'Brak tematu') AS topic_title,
            COALESCE(th.full_name, 'Brak terapeuty') AS therapist_name,
            (SELECT json_agg(json_build_object('id', c.id, 'name', c.full_name))
             FROM tus_group_members gm
             JOIN clients c ON c.id = gm.client_id
             WHERE gm.group_id = g.id
               AND gm.is_active = true
               AND s.session_date >= COALESCE(gm.join_date, '2000-01-01'::date)
               AND (gm.leave_date IS NULL OR s.session_date <= gm.leave_date)
            ) AS members
        FROM 
            tus_sessions s
        JOIN 
            tus_groups g ON s.group_id = g.id
        LEFT JOIN 
            tus_topics t ON s.topic_id = t.id
        LEFT JOIN 
            therapists th ON g.therapist_id = th.id
        WHERE 
            to_char(s.session_date, 'YYYY-MM') = :month
        ORDER BY 
            s.session_date, s.session_time;
    """)

    with engine.begin() as conn:
        rows = conn.execute(sql, {"month": month_key}).mappings().all()
        results = []
        for row in rows:
            r_dict = dict(row)
            r_dict['session_date'] = r_dict['session_date'].isoformat()
            r_dict['session_time'] = r_dict['session_time'].strftime('%H:%M:%S') if r_dict['session_time'] else None
            # Zapewnij pustą tablicę, jeśli brak członków
            r_dict['members'] = r_dict['members'] or []
            results.append(r_dict)

        return jsonify(results)

# @app.get("/api/therapists/<int:tid>/schedule")
# def therapist_schedule(tid):
#    mk = request.args.get("month")
#    if not mk:
#        return jsonify({"error": "Parametr 'month' jest wymagany."}), 400

#    all_results = []

#    with engine.begin() as conn:
#        # Query 1: Individual sessions
#        # FIX: Explicitly convert timestamp to UTC
#        sql_individual = text("""
#            SELECT
#                ss.id AS slot_id, 'individual' as type, ss.kind,
#                ss.starts_at AT TIME ZONE 'UTC' as starts_at,
#                ss.ends_at AT TIME ZONE 'UTC' as ends_at,
#                ss.status, c.full_name AS client_name,
#                ss.place_to, g.label AS group_name
#            FROM schedule_slots ss
#            JOIN clients c ON c.id = ss.client_id
#            LEFT JOIN event_groups g ON g.id = ss.group_id
#            WHERE ss.therapist_id = :tid
#              AND to_char(ss.starts_at AT TIME ZONE 'Europe/Warsaw', 'YYYY-MM') = :mk
#        """)
#        individual_rows = conn.execute(sql_individual, {"tid": tid, "mk": mk}).mappings().all()
#        all_results.extend(individual_rows)

# Query 2: TUS group sessions
# FIX: Explicitly create and convert timestamp to UTC
#        sql_tus = text("""
#            SELECT
#                s.id AS slot_id, 'tus' as type, 'therapy' as kind,
#                ((s.session_date + COALESCE(s.session_time, '00:00:00'::time)) AT TIME ZONE 'Europe/Warsaw') AT TIME ZONE 'UTC' AS starts_at,
#                ((s.session_date + COALESCE(s.session_time, '00:00:00'::time) + INTERVAL '60 minutes') AT TIME ZONE 'Europe/Warsaw') AT TIME ZONE 'UTC' AS ends_at,
#                'planned' as status, g.name AS client_name,
#                'Poradnia' as place_to, g.name AS group_name
#            FROM tus_sessions s
#            JOIN tus_groups g ON s.group_id = g.id
#            WHERE (g.therapist_id = :tid OR g.assistant_therapist_id = :tid)
#              AND to_char(s.session_date, 'YYYY-MM') = :mk
#        """)
#        tus_rows = conn.execute(sql_tus, {"tid": tid, "mk": mk}).mappings().all()
#        all_results.extend(tus_rows)

# Sorting will now work correctly
#    all_results.sort(key=lambda r: r.get('starts_at') or datetime.max.replace(tzinfo=ZoneInfo("UTC")))

# Formatting the dates to strings for the frontend
#    results = [
#        {**r,
#         'starts_at': r['starts_at'].isoformat() if r.get('starts_at') else None,
#         'ends_at': r['ends_at'].isoformat() if r.get('ends_at') else None
#         } for r in all_results
#    ]
#    return jsonify(results)

# POPRAWIONE SORTOWANIE - konwertuj wszystkie daty do tej samej strefy czasowej

@app.get("/api/therapists/<int:tid>")
def get_therapist_details(tid):
    with SessionLocal() as s:
        t = s.query(Therapist).filter(Therapist.id == tid).first()
        if not t:
            return jsonify({"error": "Terapeuta nie istnieje"}), 404
        return jsonify({
            "id": t.id,
            "full_name": t.full_name,
            "specialization": t.specialization,
            "phone": t.phone,
            "email": t.email,
            "active": t.active,
        })


@app.get("/api/therapists/<int:tid>/schedule")
@login_required
def therapist_schedule(tid):
    mk = request.args.get("month")
    if not mk:
        return jsonify({"error": "Parametr 'month' jest wymagany."}), 400

    current_firma_id = session.get('firma_id', 1)
    all_results = []

    with engine.begin() as conn:
        # 1. Wizyty indywidualne z filtrem firmy
        sql_individual = text("""
                SELECT
                    ss.id AS slot_id, 'individual' as type, ss.kind,
                    ss.starts_at, ss.ends_at, ss.status, c.full_name AS client_name,
                    ss.place_to, g.label AS group_name, g.id::text as group_id,
                    CASE WHEN t.email IS NOT NULL AND t.email != '' THEN true ELSE false END as therapist_has_email
                FROM schedule_slots ss
                JOIN clients c ON c.id = ss.client_id
                JOIN therapists t ON ss.therapist_id = t.id
                LEFT JOIN event_groups g ON g.id = CAST(ss.group_id AS UUID)
                WHERE ss.therapist_id = :tid
                  AND ss.firma_id = :fid
                  AND to_char(ss.starts_at AT TIME ZONE 'Europe/Warsaw', 'YYYY-MM') = :mk
            """)
        all_results.extend(conn.execute(sql_individual, {"tid": tid, "mk": mk, "fid": current_firma_id}).mappings().all())

        # 2. Sesje grupowe TUS z filtrem firmy
        sql_tus = text("""
                SELECT
                    s.id AS slot_id, 'tus' as type, 'therapy' as kind,
                    (s.session_date::timestamp + COALESCE(s.session_time, '00:00:00')::interval) AT TIME ZONE 'Europe/Warsaw' AS starts_at,
                    (s.session_date::timestamp + COALESCE(s.session_time, '00:00:00')::interval + INTERVAL '60 minutes') AT TIME ZONE 'Europe/Warsaw' AS ends_at,
                    'planned' as status, g.name AS client_name, 'Poradnia' as place_to, g.name AS group_name, g.id::text as group_id,
                    CASE WHEN t.email IS NOT NULL AND t.email != '' THEN true ELSE false END as therapist_has_email
                FROM tus_sessions s
                JOIN tus_groups g ON s.group_id = g.id
                LEFT JOIN therapists t ON t.id = :tid 
                WHERE (g.therapist_id = :tid OR g.assistant_therapist_id = :tid)
                  AND s.firma_id = :fid
                  AND to_char(s.session_date, 'YYYY-MM') = :mk
            """)
        all_results.extend(conn.execute(sql_tus, {"tid": tid, "mk": mk, "fid": current_firma_id}).mappings().all())

    # Formatowanie strefy czasowej
    for r in all_results:
        if not isinstance(r, dict): r = dict(r)
        if r.get('starts_at') and r['starts_at'].tzinfo is None:
            r['starts_at'] = r['starts_at'].replace(tzinfo=TZ)

    final_list = [dict(row) for row in all_results]
    final_list.sort(key=lambda r: r.get('starts_at') or datetime.max.replace(tzinfo=TZ))

    results = []
    for row_dict in final_list:
        if starts_at_aware := row_dict.get('starts_at'):
            row_dict['starts_at'] = starts_at_aware.astimezone(TZ).strftime('%Y-%m-%d %H:%M:%S')
        if ends_at_aware := row_dict.get('ends_at'):
            row_dict['ends_at'] = ends_at_aware.astimezone(TZ).strftime('%Y-%m-%d %H:%M:%S')
        results.append(row_dict)

    return jsonify(results)


@app.post("/api/schedule/group")
@login_required
def create_group_with_slots():
    """Tworzy kompletny pakiet (przywóz, terapia, odwóz) trwale przypisany do firma_id sesji."""
    data = request.get_json(silent=True) or {}
    gid = uuid.uuid4()
    status = data.get("status", "planned")
    
    # PERMANENTNA POPRAWKA: Pobranie aktywnej firmy z sesji
    current_firma_id = session.get('firma_id', 1)

    try:
        with engine.begin() as conn:
            # 1) Utwórz nadrzędny pakiet w event_groups z firma_id
            conn.execute(text("""
                INSERT INTO event_groups (id, client_id, label, firma_id)
                VALUES (:id, :client_id, :label, :firma_id)
            """), {
                "id": gid, "client_id": data["client_id"], "label": data.get("label"), "firma_id": current_firma_id
            })

            # 2) Utwórz slot terapii z firma_id
            t = data["therapy"]
            ts = datetime.fromisoformat(t["starts_at"]).replace(tzinfo=TZ)
            te = datetime.fromisoformat(t["ends_at"]).replace(tzinfo=TZ)
            session_id = ensure_shared_session_id_for_therapist(conn, int(t["therapist_id"]), ts, te)

            therapy_slot_id = conn.execute(text("""
                INSERT INTO schedule_slots (
                    group_id, client_id, therapist_id, kind, starts_at, ends_at, place_to, status, session_id, firma_id
                ) VALUES (
                    :group_id, :client_id, :therapist_id, 'therapy', :starts_at, :ends_at, :place, :status, :session_id, :firma_id
                ) RETURNING id
            """), {
                "group_id": str(gid), "client_id": data["client_id"], "therapist_id": t["therapist_id"],
                "starts_at": ts, "ends_at": te, "place": t.get("place"), "status": status, "session_id": session_id,
                "firma_id": current_firma_id
            }).scalar_one()

            # 3) Utwórz wpis o obecności z firma_id
            if therapy_slot_id:
                conn.execute(text("INSERT INTO individual_session_attendance (slot_id, status, firma_id) VALUES (:slot_id, 'obecny', :firma_id)"), 
                             {"slot_id": therapy_slot_id, "firma_id": current_firma_id})

            # Funkcja wewnętrzna wykonująca rygorystyczny insert transportów
            def insert_run(run_data, kind):
                if not run_data: return
                s = datetime.fromisoformat(run_data["starts_at"]).replace(tzinfo=TZ)
                e = datetime.fromisoformat(run_data["ends_at"]).replace(tzinfo=TZ)
                run_id = ensure_shared_run_id_for_driver(conn, int(run_data["driver_id"]), s, e)

                place_from = run_data.get("from")
                place_to = run_data.get("to")
                distance = get_route_distance(place_from, place_to) if place_from and place_to else 0

                conn.execute(text("""
                    INSERT INTO schedule_slots (
                        group_id, client_id, driver_id, vehicle_id, kind, starts_at, ends_at, place_from, place_to, status, run_id, distance_km, firma_id
                    ) VALUES (
                        :group_id, :client_id, :driver_id, :vehicle_id, :kind, :starts_at, :ends_at, :from, :to, :status, :run_id, :distance, :firma_id
                    )
                """), {
                    "group_id": str(gid), "client_id": data["client_id"], "driver_id": run_data["driver_id"],
                    "vehicle_id": run_data.get("vehicle_id"), "kind": kind, "starts_at": s, "ends_at": e,
                    "from": place_from, "to": place_to, "status": status, "run_id": run_id, "distance": distance,
                    "firma_id": current_firma_id
                })

            insert_run(data.get("pickup"), "pickup")
            insert_run(data.get("dropoff"), "dropoff")

            return jsonify({"group_id": str(gid), "ok": True}), 201

    except Exception as e:
        print(f"❌ Błąd zapisu pakietu grupowego: {e}")
        return jsonify({"error": str(e)}), 500


@app.route('/api/schedule', methods=['POST'])
@login_required
def create_schedule_slot():
    """Tworzy nową wizytę w harmonogramie z automatycznym przypisaniem aktywnego firma_id."""
    data = request.get_json(silent=True) or {}
    
    # PERMANENTNA POPRAWKA: Pobieramy firmę z sesji zalogowanego użytkownika
    current_firma_id = session.get('firma_id', 1)
    print(f"=== CREATE SCHEDULE SLOT === Firma: {current_firma_id} | Dane: {data}")

    kind = data.get('kind')
    starts_at_str = data.get('starts_at')
    ends_at_str = data.get('ends_at')
    client_id = data.get('client_id')
    therapist_id = data.get('therapist_id')
    driver_id = data.get('driver_id')

    if not starts_at_str or not ends_at_str or not kind:
        return jsonify({"error": "Brak podstawowych pól: czas startu/końca lub rodzaj (kind)."}), 400

    if kind in ['therapy', 'pickup', 'dropoff']:
        if not client_id:
            return jsonify({"error": "Wybierz klienta."}), 400
        if kind == 'therapy' and not therapist_id:
            return jsonify({"error": "Wybierz terapeutę."}), 400
        if kind in ['pickup', 'dropoff'] and not driver_id:
            return jsonify({"error": "Wybierz kierowcę."}), 400
    else:
        return jsonify({"error": f"Nieznany typ wizyty: {kind}"}), 400

    try:
        def parse_local_time(date_str):
            clean_str = date_str.replace(' ', 'T').replace('Z', '')
            dt = datetime.fromisoformat(clean_str)
            return dt.replace(tzinfo=TZ)

        starts_at = parse_local_time(starts_at_str)
        ends_at = parse_local_time(ends_at_str)

        with engine.begin() as conn:
            # Sprawdzanie kolizji z uwzględnieniem firmy
            if kind == 'therapy':
                conflicts = find_overlaps(conn, therapist_id=therapist_id, starts_at=starts_at, ends_at=ends_at, firma_id=current_firma_id)
                if conflicts:
                    conflict_details = []
                    for c in conflicts:
                        conflict_details.append({
                            "id": c['id'], "client_name": c.get('client_name', 'Nieznany klient'),
                            "starts_at": c['starts_at'].astimezone(TZ).isoformat(),
                            "ends_at": c['ends_at'].astimezone(TZ).isoformat(), "kind": c.get('kind', 'therapy')
                        })
                    return jsonify({"error": "Konflikt czasowy", "conflicts": conflict_details}), 409

            new_slot_id = None
            event_group_uuid = uuid.uuid4()

            if kind == 'therapy':
                # Zapis grupy z wymuszeniem firma_id
                conn.execute(text("""
                    INSERT INTO event_groups (id, client_id, label, firma_id)
                    VALUES (:id, :client_id, :label, :firma_id)
                """), {
                    "id": event_group_uuid, "client_id": client_id, 
                    "label": f"Terapia {client_id} - {starts_at.strftime('%Y-%m-%d %H:%M')}",
                    "firma_id": current_firma_id
                })
                
                session_id = ensure_shared_session_id_for_therapist(conn, therapist_id, starts_at, ends_at)
                
                # Zapis slotu z wymuszeniem firma_id
                new_slot_id = conn.execute(text("""
                    INSERT INTO schedule_slots (
                        group_id, client_id, therapist_id, kind, starts_at, ends_at, place_to, status, session_id, firma_id
                    ) VALUES (
                        :group_id, :client_id, :therapist_id, :kind, :starts_at, :ends_at, :place_to, :status, :session_id, :firma_id
                    ) RETURNING id
                """), {
                    "group_id": str(event_group_uuid), "client_id": client_id, "therapist_id": therapist_id,
                    "kind": kind, "starts_at": starts_at, "ends_at": ends_at, 
                    "place_to": data.get('place_to', 'Poradnia'), "status": data.get('status', 'planned'),
                    "session_id": session_id, "firma_id": current_firma_id
                }).scalar_one()
                
                # Zapis obecności z wymuszeniem firma_id
                conn.execute(text("INSERT INTO individual_session_attendance (slot_id, status, firma_id) VALUES (:slot_id, 'obecny', :firma_id)"), 
                             {"slot_id": new_slot_id, "firma_id": current_firma_id})
                log_activity("DODANIE_TERAPII", f"Dodano terapię ID: {new_slot_id} (Firma: {current_firma_id})")

            elif kind in ['pickup', 'dropoff']:
                place_from = data.get('place_from', '')
                place_to = data.get('place_to', '')
                
                dist_km = 0
                if place_from and place_to:
                    calc = get_route_distance(place_from, place_to)
                    dist_km = float(calc) if calc else 0
                
                conn.execute(text("""
                    INSERT INTO event_groups (id, client_id, label, firma_id)
                    VALUES (:id, :client_id, :label, :firma_id)
                """), {
                    "id": event_group_uuid, "client_id": client_id, 
                    "label": f"Transport - {starts_at.strftime('%Y-%m-%d %H:%M')}",
                    "firma_id": current_firma_id
                })

                new_slot_id = conn.execute(text("""
                    INSERT INTO schedule_slots (
                        group_id, client_id, driver_id, kind, starts_at, ends_at, place_from, place_to, distance_km, status, firma_id
                    ) VALUES (
                        :group_id, :client_id, :driver_id, :kind, :starts_at, :ends_at, :place_from, :place_to, :distance_km, :status, :firma_id
                    ) RETURNING id
                """), {
                    "group_id": str(event_group_uuid), "client_id": client_id, "driver_id": driver_id,
                    "kind": kind, "starts_at": starts_at, "ends_at": ends_at, 
                    "place_from": place_from, "place_to": place_to, "distance_km": dist_km,
                    "status": data.get('status', 'planned'), "firma_id": current_firma_id
                }).scalar_one()
                
                log_activity("DODANIE_TRANSPORTU", f"Dodano kurs ID: {new_slot_id} (Firma: {current_firma_id})")

            # Powiadomienia e-mail
            if kind == 'therapy' and therapist_id:
                try:
                    info = conn.execute(text("""
                        SELECT t.email, c.full_name as client_name
                        FROM therapists t LEFT JOIN clients c ON c.id = :cid WHERE t.id = :tid
                    """), {"cid": client_id, "tid": therapist_id}).mappings().first()
                    if info and info['email'] and '@' in info['email']:
                        body_html = f"<h3>Witaj,</h3><p>Dodano nową wizytę: {info['client_name']} w dniu {starts_at.strftime('%d.%m.%Y')} o {starts_at.strftime('%H:%M')}.</p>"
                        send_email_async(info['email'], "Nowa wizyta w grafiku", body_html)
                except Exception as mail_error:
                    print(f"⚠️ Błąd maila: {mail_error}")

            return jsonify({"success": True, "slot_id": new_slot_id, "message": "Zapisano pomyślnie."}), 201

    except Exception as e:
        print(f"❌ Błąd tworzenia wizyty: {str(e)}")
        return jsonify({"error": f"Błąd wewnętrzny: {str(e)}"}), 500


# --- ENDPOINTY DLA PLANU TUS ---

@app.route('/api/tus/groups/<int:group_id>/plan', methods=['GET'])
@login_required
def get_tus_group_plan(group_id):
    """Pobiera plan zajęć dla danej grupy."""
    try:
        with session_scope() as session:
            # Pobieramy pozycje planu posortowane po dacie
            items = session.query(TUSPlanItem) \
                .filter_by(group_id=group_id) \
                .order_by(TUSPlanItem.planned_date).all()

            return jsonify([{
                'id': i.id,
                'semester': i.semester,
                'planned_date': i.planned_date.isoformat(),
                'topic': i.topic,
                'is_executed': i.is_executed
            } for i in items]), 200
    except Exception as e:
        return jsonify({'error': str(e)}), 500


@app.route('/api/ai/generate-client-report', methods=['POST'])
@login_required
def generate_client_report_ai():
    data = request.get_json()
    # 1. Pobieramy dane, ale NIE używamy ich wprost w zapytaniu do AI
    real_client_name = data.get('client_name', 'Klient')
    period = data.get('period', 'okres')
    notes_list = data.get('notes', [])

    if not notes_list:
        return jsonify({'report': 'Brak danych do analizy.'})

    # 2. PSEUDONIMIZACJA DANYCH
    # Zamiast prawdziwego imienia, używamy pseudonimu w komunikacji z AI
    pseudo_name = "Pacjent"

    # 3. CZYSZCZENIE NOTATEK (Prosta anonimizacja)
    # Usuwamy wystąpienia prawdziwego imienia i nazwiska z treści notatek
    clean_notes = []
    for note in notes_list:
        # Zamień imię/nazwisko na "Pacjent" (niezależnie od wielkości liter)
        safe_note = note.replace(real_client_name, pseudo_name)
        # Możesz tu dodać więcej reguł, np. usuwanie numerów telefonów regexem
        clean_notes.append(safe_note)

    notes_context = "\n".join(clean_notes)

    # 4. NOWY, BEZPIECZNY PROMPT
    prompt = f"""
    Jesteś profesjonalnym psychoterapeutą / psychologiem.
    Twoim zadaniem jest przygotowanie WSTĘPU DO OPINII o funkcjonowaniu podopiecznego na podstawie zanonimizowanych notatek z sesji.

    DANE:
    Podmiot: {pseudo_name} (dane zanonimizowane)
    Okres raportu: {period}

    ZANONIMIZOWANE NOTATKI Z SESJI:
    {notes_context}

    INSTRUKCJA:
    1. Przeanalizuj powyższe notatki. Szukaj powtarzających się motywów, postępów, trudności oraz realizowanych tematów.
    2. Napisz profesjonalną, syntetyczną opinię (ok. 300-500 słów).
    3. Styl: formalny, kliniczny, empatyczny. Używaj sformułowań typu "Obserwuje się...", "W toku pracy terapeutycznej...", "Podopieczny wykazuje...".
    4. NIE używaj w odpowiedzi żadnych imion ani nazwisk, stosuj formy bezosobowe lub "Pacjent/Podopieczny".
    5. Podziel tekst na sekcje:
       - Obszary pracy (nad czym pracowano)
       - Funkcjonowanie emocjonalno-społeczne (wnioski z obserwacji)
       - Postępy i zasoby
       - Zalecenia do dalszej pracy (jeśli wynikają z notatek)

    Ważne: Opieraj się TYLKO na dostarczonych notatkach. Nie wymyślaj faktów.
    """

    try:
        import google.generativeai as genai
        api_key = os.getenv("GOOGLE_AI_API_KEY")

        if not api_key:
            return jsonify({'error': 'Błąd konfiguracji serwera (brak klucza AI).'}), 500

        genai.configure(api_key=api_key)

        # Używamy modelu flash dla szybkości
        model = genai.GenerativeModel('gemini-3.5-flash')

        response = model.generate_content(prompt)
        report_text = response.text

        # 5. DE-PSEUDONIMIZACJA (Opcjonalne - przywrócenie imienia w wyniku)
        # Możemy zamienić "Pacjent" z powrotem na imię klienta, aby terapeuta miał gotowy tekst
        # Ale bezpieczniej jest zostawić "Pacjent", aby terapeuta sam wpisał dane w dokumencie końcowym.
        # Tu dla wygody przywracamy:
        final_report = report_text.replace(pseudo_name, real_client_name)

        return jsonify({'report': final_report})

    except Exception as e:
        print(f"Błąd AI: {e}")
        return jsonify({'error': 'Wystąpił błąd podczas generowania opinii.'}), 500

@app.route('/api/tus/groups/<int:group_id>/generate-ai-plan', methods=['POST'])
@login_required
def generate_tus_group_plan_ai(group_id):
    data = request.get_json()
    start_date_str = data.get('start_date')
    end_date_str = data.get('end_date')  # Nowy parametr
    day_of_week = data.get('day_of_week')  # Nowy parametr (np. "2" dla wtorku)
    time_of_day = data.get('time_of_day')  # Nowy parametr (np. "16:00")
    semester = data.get('semester', 1)

    if not start_date_str or not end_date_str:
        return jsonify({'error': 'Wymagany zakres dat'}), 400

    try:
        with session_scope() as session:
            # 1. Pobierz grupę i uczestników
            group = session.query(TUSGroup).options(
                joinedload(TUSGroup.member_associations).joinedload(TUSGroupMember.client)
            ).filter(TUSGroup.id == group_id).first()

            if not group:
                return jsonify({'error': 'Grupa nie istnieje'}), 404

            # 2. Zbuduj profile uczestników
            participants_profiles = []
            has_diagnoses = False
            for member in group.members:
                diag = member.diagnosis if member.diagnosis else 'Brak'
                notes = member.admission_notes if member.admission_notes else 'Brak'
                if diag != 'Brak' or notes != 'Brak':
                    has_diagnoses = True

                profile = f"- {member.full_name} (Wiek: {member.age or '?'}). Diagnoza: {diag}. Trudności: {notes}."
                participants_profiles.append(profile)

            participants_text = "\n".join(participants_profiles)

            # 3. Logika generowania dat w Pythonie (zamiast prosić o to AI)
            # To jest bezpieczniejsze i dokładniejsze.
            from datetime import datetime, timedelta

            start_dt = datetime.strptime(start_date_str, "%Y-%m-%d")
            end_dt = datetime.strptime(end_date_str, "%Y-%m-%d")
            target_weekday = int(day_of_week) - 1  # Python: 0=Pon, HTML: 1=Pon

            generated_dates = []
            current_dt = start_dt
            while current_dt <= end_dt:
                if current_dt.weekday() == target_weekday:
                    # Dodajemy godzinę jeśli jest podana
                    if time_of_day:
                        full_date_str = f"{current_dt.strftime('%Y-%m-%d')} {time_of_day}"
                    else:
                        full_date_str = current_dt.strftime('%Y-%m-%d')
                    generated_dates.append(full_date_str)
                current_dt += timedelta(days=1)

            if not generated_dates:
                return jsonify({'error': 'W wybranym zakresie dat nie ma wskazanego dnia tygodnia.'}), 400

            sessions_count = len(generated_dates)

            # 4. Prompt dla AI
            import google.generativeai as genai
            api_key = os.getenv("GOOGLE_AI_API_KEY")
            genai.configure(api_key=api_key)
            model = genai.GenerativeModel('gemini-3.5-flash')

            prompt = f"""
            Jesteś superwizorem TUS. Stwórz plan na {sessions_count} spotkań.

            UCZESTNICY:
            {participants_text}

            INSTRUKCJA:
            1. Przeanalizuj diagnozy. Sprawdź zalecenia do pracy. Na tej podstawie przygutj plan. Jeśli ich brakuje, plan ma być ogólnorozwojowy.
            2. Wygeneruj DOKŁADNIE {sessions_count} tematów, pasujących do liczby dat.
            3. Na początku odpowiedzi dodaj pole "meta_info", w którym napiszesz, czy plan bazuje na diagnozach, czy jest ogólny (bo brak danych).

            FORMAT JSON:
            {{
                "meta_info": "Tutaj komunikat dla terapeuty...",
                "topics": [
                    {{ "topic": "Temat 1", "rationale": "Cel..." }},
                    {{ "topic": "Temat 2", "rationale": "Cel..." }}
                    ... (dokładnie {sessions_count} elementów)
                ]
            }}
            """

            response = model.generate_content(prompt, generation_config={"response_mime_type": "application/json"})

            import json
            try:
                ai_data = json.loads(response.text)
                topics_list = ai_data.get('topics', [])
                meta_info = ai_data.get('meta_info', 'Plan wygenerowany automatycznie.')

                final_plan = []
                # Łączymy daty z tematami
                for i, date_str in enumerate(generated_dates):
                    if i < len(topics_list):
                        topic_data = topics_list[i]
                        final_plan.append({
                            'date': date_str,
                            'topic': topic_data['topic'],
                            'rationale': topic_data['rationale'],
                            'semester': semester
                        })

                return jsonify({'plan': final_plan, 'info': meta_info})

            except json.JSONDecodeError:
                return jsonify({'error': 'Błąd przetwarzania odpowiedzi AI'}), 500

    except Exception as e:
        print(f"AI Plan Error: {e}")
        return jsonify({'error': str(e)}), 500


@app.route('/api/tus/plans', methods=['POST'])
@login_required
def add_tus_plan_item():
    """Dodaje nową pozycję do planu."""
    data = request.get_json()
    try:
        with session_scope() as session:
            # Konwersja daty string -> object
            p_date = datetime.fromisoformat(data['planned_date']).date()

            new_item = TUSPlanItem(
                group_id=data['group_id'],
                semester=data.get('semester', 1),
                planned_date=p_date,
                topic=data['topic'],
                is_executed=False
            )
            session.add(new_item)
            # Commit dzieje się automatycznie przy wyjściu z session_scope

        return jsonify({'message': 'Dodano do planu'}), 201
    except Exception as e:
        print(f"Błąd dodawania planu: {e}")
        return jsonify({'error': str(e)}), 500


@app.route('/api/tus/plans/<int:item_id>', methods=['PUT'])
@login_required
def update_tus_plan_item(item_id):
    """Aktualizuje pozycję w planie pracy ORAZ synchronizuje powiązaną sesję."""
    data = request.get_json()
    try:
        with session_scope() as session:
            item = session.query(TUSPlanItem).get(item_id)
            if not item:
                return jsonify({'error': 'Nie znaleziono pozycji'}), 404

            # --- 1. AKTUALIZACJA PLANU ---
            if 'planned_date' in data:
                item.planned_date = datetime.fromisoformat(data['planned_date']).date()

            if 'semester' in data:
                item.semester = int(data['semester'])

            new_topic_title = None
            if 'topic' in data:
                new_topic_title = data['topic'].strip()
                item.topic = new_topic_title

            # --- 2. SYNCHRONIZACJA SESJI ---
            # Jeśli zmieniliśmy temat, musimy zaktualizować też sesję (dziennik)
            if new_topic_title:
                # Szukamy sesji połączonej "twardym" linkiem (plan_item_id)
                linked_session = session.query(TUSSession).filter(
                    TUSSession.plan_item_id == item.id
                ).first()

                # FALLBACK: Jeśli to stara sesja bez linku, spróbujmy znaleźć ją po dacie i grupie
                # i od razu naprawmy brakujący link
                if not linked_session:
                    linked_session = session.query(TUSSession).filter(
                        TUSSession.group_id == item.group_id,
                        TUSSession.session_date == item.planned_date
                    ).first()
                    if linked_session:
                        linked_session.plan_item_id = item.id  # Naprawiamy link na przyszłość

                # Jeśli znaleźliśmy sesję, aktualizujemy jej temat
                if linked_session:
                    # Sprawdź czy temat TUS istnieje w słowniku, jak nie to stwórz
                    topic_obj = session.query(TUSTopic).filter(
                        func.lower(TUSTopic.title) == new_topic_title.lower()
                    ).first()

                    if not topic_obj:
                        topic_obj = TUSTopic(title=new_topic_title)
                        session.add(topic_obj)
                        session.flush()

                    linked_session.topic_id = topic_obj.id
                    print(f"✅ Zsynchronizowano temat w sesji ID: {linked_session.id}")

            # Commit dzieje się automatycznie przy wyjściu z session_scope

        return jsonify({'message': 'Zaktualizowano plan i zsynchronizowano sesję'}), 200

    except Exception as e:
        print(f"Błąd aktualizacji planu: {e}")
        import traceback
        traceback.print_exc()
        return jsonify({'error': str(e)}), 500


@app.route('/api/tus/groups/<int:group_id>/plans', methods=['DELETE'])
@login_required
def delete_all_tus_plans(group_id):
    """Usuwa WSZYSTKIE pozycje z planu dla danej grupy."""
    try:
        with session_scope() as session:
            # Usuwamy wszystkie wpisy TUSPlanItem dla tej grupy
            deleted_count = session.query(TUSPlanItem).filter(
                TUSPlanItem.group_id == group_id
            ).delete()

            print(f"🗑️ Usunięto {deleted_count} pozycji planu dla grupy {group_id}")

        return jsonify({'message': f'Usunięto {deleted_count} pozycji'}), 200

    except Exception as e:
        print(f"Błąd usuwania planu: {e}")
        return jsonify({'error': str(e)}), 500

@app.route('/api/tus/plans/<int:item_id>', methods=['DELETE'])
@login_required
def delete_tus_plan_item(item_id):
    """Usuwa pozycję z planu."""
    try:
        with session_scope() as session:
            item = session.query(TUSPlanItem).get(item_id)
            if not item:
                return jsonify({'error': 'Nie znaleziono pozycji'}), 404

            session.delete(item)
        return jsonify({}), 204
    except Exception as e:
        return jsonify({'error': str(e)}), 500

@app.route('/api/schedule/<int:slot_id>', methods=['GET', 'PUT', 'PATCH', 'DELETE'])
@login_required
def handle_single_schedule_slot(slot_id):
    """
    Centralny, bezpieczny kontroler zarządzania pojedynczą wizytą (SaaS Secure).
    Rozwiązuje błąd 500 RowMapping oraz zapobiega konfliktom wizyty z samą sobą.
    """
    current_firma_id = session.get('firma_id', 1)

    # --- 1. GET: Pobieranie szczegółów do okna edycji ---
    if request.method == 'GET':
        try:
            with engine.connect() as conn:
                slot = conn.execute(text("""
                    SELECT 
                        ss.id, ss.group_id, ss.client_id, ss.therapist_id, 
                        ss.driver_id, ss.kind, ss.starts_at, ss.ends_at,
                        ss.place_to, ss.status, ss.distance_km,
                        c.full_name as client_name,
                        t.full_name as therapist_name,
                        d.full_name as driver_name,
                        eg.label as group_label
                    FROM schedule_slots ss
                    LEFT JOIN clients c ON c.id = ss.client_id
                    LEFT JOIN therapists t ON t.id = ss.therapist_id
                    LEFT JOIN drivers d ON d.id = ss.driver_id
                    LEFT JOIN event_groups eg ON eg.id = ss.group_id::uuid
                    WHERE ss.id = :id AND ss.firma_id = :fid
                """), {"id": slot_id, "fid": current_firma_id}).mappings().first()

                if not slot:
                    return jsonify({"error": "Wizyta nie znaleziona lub brak uprawnień."}), 404

                slot_dict = dict(slot)
                if slot_dict['starts_at']: slot_dict['starts_at'] = slot_dict['starts_at'].isoformat()
                if slot_dict['ends_at']: slot_dict['ends_at'] = slot_dict['ends_at'].isoformat()
                return jsonify(slot_dict), 200
        except Exception as e:
            return jsonify({"error": str(e)}), 500

    # --- 2. PUT / PATCH: Aktualizacja danych wizyty ---
    elif request.method in ('PUT', 'PATCH'):
        data = request.get_json(silent=True) or {}
        try:
            with engine.begin() as conn:
                old_slot = conn.execute(
                    text("SELECT * FROM schedule_slots WHERE id = :id AND firma_id = :fid"),
                    {"id": slot_id, "fid": current_firma_id}
                ).mappings().first()

                if not old_slot:
                    return jsonify({"error": "Modyfikowany obiekt nie istnieje w tym podmiocie."}), 404

                update_fields = []
                params = {"id": slot_id, "fid": current_firma_id}
                time_changed = False
                
                # POPRAWKA MAPOWANIA: Bezpieczny dostęp słownikowy [field] zamiast kropki
                new_start_dt = old_slot['starts_at']
                new_end_dt = old_slot['ends_at']

                if 'starts_at' in data and data['starts_at']:
                    s_dt = datetime.fromisoformat(data['starts_at'].replace(' ', 'T').replace('Z', ''))
                    new_start_dt = s_dt.replace(tzinfo=TZ) if s_dt.tzinfo is None else s_dt.astimezone(TZ)
                    params['starts_at'] = new_start_dt
                    update_fields.append("starts_at = :starts_at")
                    if new_start_dt != old_slot['starts_at']: time_changed = True

                if 'ends_at' in data and data['ends_at']:
                    e_dt = datetime.fromisoformat(data['ends_at'].replace(' ', 'T').replace('Z', ''))
                    new_end_dt = e_dt.replace(tzinfo=TZ) if e_dt.tzinfo is None else e_dt.astimezone(TZ)
                    params['ends_at'] = new_end_dt
                    update_fields.append("ends_at = :ends_at")
                    if new_end_dt != old_slot['ends_at']: time_changed = True

                kind = data.get('kind', old_slot['kind'])
                therapist_id = data.get('therapist_id', old_slot['therapist_id'])
                if therapist_id: therapist_id = int(therapist_id)

                if kind == 'therapy' and therapist_id and time_changed:
                    conflicts = find_overlaps(conn, therapist_id=therapist_id, starts_at=new_start_dt, ends_at=new_end_dt, exclude_slot_id=slot_id)
                    if conflicts:
                        return jsonify({"error": "Konflikt czasowy z inną aktywnością terapeuty."}), 409

                if 'client_id' in data and data['client_id']:
                    params['cid'] = int(data['client_id'])
                    update_fields.append("client_id = :cid")
                if 'status' in data:
                    params['status'] = data['status']
                    update_fields.append("status = :status")
                if 'place_to' in data:
                    params['place_to'] = data['place_to']
                    update_fields.append("place_to = :place_to")
                if 'driver_id' in data:
                    params['did'] = int(data['driver_id']) if data['driver_id'] else None
                    update_fields.append("driver_id = :did")

                if update_fields:
                    sql = f"UPDATE schedule_slots SET {', '.join(update_fields)} WHERE id = :id AND firma_id = :fid"
                    conn.execute(text(sql), params)

                return jsonify({"success": True, "message": "Zaktualizowano pomyślnie"}), 200
        except Exception as e:
            print(f"❌ Wyjątek edycji slotu 500: {e}")
            return jsonify({"error": str(e)}), 500

    # --- 3. DELETE: Trwałe usuwanie wizyty ---
    elif request.method == 'DELETE':
        try:
            with engine.begin() as conn:
                slot = conn.execute(text("SELECT * FROM schedule_slots WHERE id = :id AND firma_id = :fid"), {"id": slot_id, "fid": current_firma_id}).mappings().first()
                if not slot:
                    return jsonify({"error": "Obiekt nie istnieje lub brak uprawnień."}), 404

                if slot['kind'] == 'therapy':
                    conn.execute(text("DELETE FROM schedule_slots WHERE client_id = :cid AND kind IN ('pickup', 'dropoff') AND date(starts_at) = date(:date) AND firma_id = :fid"), {"cid": slot['client_id'], "date": slot['starts_at'], "fid": current_firma_id})
                
                conn.execute(text("DELETE FROM schedule_slots WHERE id = :id AND firma_id = :fid"), {"id": slot_id, "fid": current_firma_id})
                return jsonify({"status": "success", "message": "Usunięto pomyślnie"}), 200
        except Exception as e:
            return jsonify({"error": str(e)}), 500


# NOWY ENDPOINT W odnowa.py
@app.get("/api/clients/<int:client_id>/tus-groups")
def get_client_tus_groups(client_id):
    """Zwraca listę grup TUS, do których należy dany klient."""
    with session_scope() as db_session:
        groups = db_session.query(TUSGroup) \
            .join(TUSGroup.member_associations) \
            .filter(TUSGroupMember.client_id == client_id) \
            .all()

        if not groups:
            return jsonify([])

        result = [{"id": group.id, "name": group.name} for group in groups]
        return jsonify(result)


# NOWE ENDPOINTY DO DODANIA W odnowa.py

@app.get("/api/tus/sessions/<int:session_id>/bonuses")
def get_session_bonuses(session_id):
    """Pobiera listę bonusów indywidualnych przyznanych w danej sesji."""
    with session_scope() as db_session:
        bonuses = db_session.query(TUSMemberBonus) \
            .filter(TUSMemberBonus.session_id == session_id).all()

        result = {b.client_id: b.points for b in bonuses}
        return jsonify(result)


@app.post("/api/tus/sessions/<int:session_id>/bonuses")
def save_session_bonuses(session_id):
    """Zapisuje 'hurtowo' bonusy indywidualne dla uczestników sesji."""
    data = request.get_json(silent=True) or {}
    bonuses_data = data.get("bonuses", [])  # Oczekujemy listy: [{"client_id": 1, "points": 5}, ...]

    with session_scope() as db_session:
        # 1. Usuń stare bonusy dla tej sesji, aby uniknąć duplikatów
        db_session.query(TUSMemberBonus).filter(TUSMemberBonus.session_id == session_id).delete()

        # 2. Dodaj nowe bonusy
        for bonus in bonuses_data:
            if bonus.get("points", 0) > 0:  # Zapisuj tylko, jeśli punkty są większe od 0
                new_bonus = TUSMemberBonus(
                    session_id=session_id,
                    client_id=bonus["client_id"],
                    points=bonus["points"]
                )
                db_session.add(new_bonus)

    return jsonify({"ok": True}), 200

@app.get("/api/tus/sessions/<int:session_id>")
def get_tus_session_details(session_id: int):
    """Zwraca szczegóły pojedynczej sesji TUS, w tym listę jej uczestników."""
    with session_scope() as db_session:
        # Krok 1: Pobierz sesję i od razu jej temat (prosta relacja)
        session_obj = db_session.query(TUSSession).options(
            joinedload(TUSSession.topic)
        ).filter(TUSSession.id == session_id).first()

        if not session_obj:
            return jsonify({"error": "Session not found"}), 404

        # Krok 2: Pobierz grupę tej sesji i jej członków
        # To zapytanie jest bezpieczniejsze i korzysta z poprawnie skonfigurowanej relacji
        group = db_session.query(TUSGroup).options(
            joinedload(TUSGroup.member_associations).joinedload(TUSGroupMember.client)
        ).filter(TUSGroup.id == session_obj.group_id).first()

        members_json = []
        if group and group.members:
            members_json = [
                {"id": member.id, "full_name": member.full_name}
                for member in group.members
            ]

            # Pobierz ID zachowań przypisanych do tej sesji
            behavior_ids = [
                row.behavior_id for row in
                db_session.query(TUSSessionBehavior.behavior_id)
                .filter(TUSSessionBehavior.session_id == session_id).all()
            ]
            # Pobierz ID obecnych klientów
            present_ids = [
                row.client_id for row in
                db_session.query(TUSSessionAttendance.client_id)
                .filter(TUSSessionAttendance.session_id == session_id, TUSSessionAttendance.status == 'obecny').all()
            ]
        # Krok 3: Zbuduj i zwróć odpowiedź
        session_data = {
            "id": session_obj.id,
            "session_date": session_obj.session_date.isoformat(),
            "topic_title": session_obj.topic.title if session_obj.topic else "Brak tematu",
            "members": members_json
        }

        return jsonify(session_data)


@app.get("/api/tus/groups/<int:group_id>/bonus-details")
def get_bonus_details(group_id: int):
    print("\n--- URUCHOMIONO get_bonus_details ---")
    print(f"--- Grupa ID: {group_id} ---")

    # POPRAWKA: Zmiana nazwy zmiennej na 'db_session' dla spójności
    with session_scope() as db_session:
        group = db_session.query(TUSGroup).options(
            joinedload(TUSGroup.member_associations).joinedload(TUSGroupMember.client)
        ).filter(TUSGroup.id == group_id).first()

        if not group:
            # ...
            return jsonify({"error": "Group not found"}), 404

        member_ids = [member.id for member in group.members]
        if not member_ids:
            return jsonify([])

        # POPRAWKA: Użycie 'db_session' we wszystkich zapytaniach
        behavior_scores_sq = db_session.query(
            TUSSessionMemberScore.client_id,
            func.sum(TUSSessionMemberScore.points).label("total_behavior")
        ).join(TUSSession, TUSSession.id == TUSSessionMemberScore.session_id) \
            .filter(TUSSession.group_id == group_id) \
            .group_by(TUSSessionMemberScore.client_id).subquery()

        session_bonuses_sq = db_session.query(
            TUSMemberBonus.client_id,
            func.sum(TUSMemberBonus.points).label("total_session_bonus")
        ).join(TUSSession, TUSSession.id == TUSMemberBonus.session_id) \
            .filter(TUSSession.group_id == group_id) \
            .group_by(TUSMemberBonus.client_id).subquery()

        general_bonuses_sq = db_session.query(
            TUSGeneralBonus.client_id,
            func.sum(TUSGeneralBonus.points).label("total_general_bonus")
        ).filter(TUSGeneralBonus.group_id == group_id) \
            .group_by(TUSGeneralBonus.client_id).subquery()

        results_query = db_session.query(
            Client.id, Client.full_name,
            func.coalesce(behavior_scores_sq.c.total_behavior, 0),
            func.coalesce(session_bonuses_sq.c.total_session_bonus, 0),
            func.coalesce(general_bonuses_sq.c.total_general_bonus, 0)
        ).outerjoin(behavior_scores_sq, Client.id == behavior_scores_sq.c.client_id) \
            .outerjoin(session_bonuses_sq, Client.id == session_bonuses_sq.c.client_id) \
            .outerjoin(general_bonuses_sq, Client.id == general_bonuses_sq.c.client_id) \
            .filter(Client.id.in_(member_ids)).order_by(Client.full_name)

        final_results = []
        for client_id, full_name, behavior_pts, session_pts, general_pts in results_query.all():
            # --- POCZĄTEK POPRAWKI ---
            # Dodaj 'behavior_pts' do sumy
            total_points = int(behavior_pts) + int(session_pts) + int(general_pts)
            # --- KONIEC POPRAWKI ---

            final_results.append({
                "client_id": client_id, "full_name": full_name,
                "behavior_points": int(behavior_pts),
                "session_bonus_points": int(session_pts),
                "general_bonus_points": int(general_pts),
                "total_points": total_points
            })

        return jsonify(final_results)


@app.post("/api/tus/groups/<int:group_id>/award-general-bonus")
@login_required  # Warto dodać, aby log_activity wiedziało kto to zrobił
def award_general_bonus(group_id: int):
    data = request.get_json(silent=True) or {}
    client_id = data.get("client_id")
    points = data.get("points")
    reason = data.get("reason", "Bez powodu")  # Domyślna wartość dla logów

    if not all([client_id, points]):
        return jsonify({"error": "client_id and points are required"}), 400

    try:
        points = int(points)
        if points <= 0:
            raise ValueError()
    except (ValueError, TypeError):
        return jsonify({"error": "Points must be a positive integer"}), 400

    # Mnożymy przyznane punkty razy 10 (zgodnie z Twoją logiką biznesową)
    final_points = points * 10

    try:
        with session_scope() as db_session:
            # 1. Sprawdź czy klient należy do grupy
            is_member = db_session.query(TUSGroupMember).filter_by(
                group_id=group_id, client_id=client_id
            ).first()

            if not is_member:
                return jsonify({"error": "Client is not a member of this group"}), 403

            # 2. Utwórz bonus
            new_bonus = TUSGeneralBonus(
                client_id=client_id,
                group_id=group_id,
                points=final_points,
                reason=reason,
                semester=int(data.get('semester', 1)),  # Pobieramy semestr
                reward_text=data.get('reward_text')
            )
            db_session.add(new_bonus)

            # 3. LOGOWANIE AKCJI
            # Pobieramy nazwisko klienta dla czytelności logu (opcjonalne, ale pomocne)
            client_name = "ID " + str(client_id)
            client_obj = db_session.get(Client, client_id)
            if client_obj:
                client_name = client_obj.full_name

            log_msg = f"Przyznano {final_points} pkt (Bonus Ogólny) dla: {client_name}. Powód: {reason}"

            # Zapisujemy log w tej samej transakcji co bonus
            # (Funkcja log_activity używa własnego session_scope, więc tu wywołujemy ją bezpiecznie)
            # Uwaga: Jeśli log_activity używa insert, tu jest OK.

            # Wstawienie logu do systemu (używamy Twojej funkcji helpera)
            try:
                log_activity("DODANIE_BONUSU_TUS", log_msg)
            except Exception as log_e:
                print(f"⚠️ Błąd zapisu logu: {log_e}")

        return jsonify({"ok": True}), 201

    except Exception as e:
        print(f"❌ Błąd przyznawania bonusu: {e}")
        import traceback
        traceback.print_exc()
        return jsonify({"error": str(e)}), 500

@app.route('/api/tus/bonuses/<int:bonus_id>', methods=['DELETE'])
@login_required
def delete_general_bonus(bonus_id):
    try:
        with session_scope() as session:
            session.query(TUSGeneralBonus).filter(TUSGeneralBonus.id == bonus_id).delete()
        return jsonify({'message': 'Bonus usunięty'}), 200
    except Exception as e:
        return jsonify({'error': str(e)}), 500


@app.get('/api/tus/groups/<int:group_id>/general-bonus-history')
@login_required
def get_general_bonus_history(group_id):
    try:
        with session_scope() as session:
            # Używamy ORM - session.query(Model)
            # To automatycznie pobiera wszystkie zdefiniowane w klasie kolumny
            bonuses = session.query(TUSGeneralBonus).options(
                joinedload(TUSGeneralBonus.client)  # Optymalizacja: pobierz klienta w jednym zapytaniu
            ).filter(
                TUSGeneralBonus.group_id == group_id
            ).order_by(TUSGeneralBonus.created_at.desc()).all()

            results = []
            for h in bonuses:
                results.append({
                    'id': h.id,
                    'client_name': h.client.full_name if h.client else "Nieznany",
                    'points': h.points,
                    'reason': h.reason,
                    # Tutaj odwołujemy się do nowych pól.
                    # Jeśli klasa jest zaktualizowana i serwer zrestartowany, to MUSI działać.
                    'semester': h.semester,
                    'reward_text': h.reward_text,
                    'date': h.created_at.strftime('%Y-%m-%d') if h.created_at else '-'
                })

            return jsonify(results)

    except Exception as e:
        print(f"BŁĄD W get_general_bonus_history: {e}")
        return jsonify({'error': str(e)}), 500


@app.put('/api/tus/groups/<int:group_id>/schedule')
def save_group_schedule(group_id):
    data = request.get_json(silent=True) or {}
    schedule_days_str = data.get('schedule_days', [])

    if not isinstance(schedule_days_str, list):
        return jsonify({"error": "Oczekiwano tablicy 'schedule_days'."}), 400

    with session_scope() as db_session:
        group = db_session.get(TUSGroup, group_id)
        if not group:
            return jsonify({"error": "Nie znaleziono grupy."}), 404

        # Konwertuj stringi na obiekty dat
        group.schedule_days = sorted([date.fromisoformat(d) for d in set(schedule_days_str)])
        db_session.commit()

    return jsonify({"ok": True})


@app.get("/api/tus/sessions-for-day")
def get_sessions_for_day():
    """Zwraca listę sesji TUS dla podanej daty."""
    date_str = request.args.get('date')
    if not date_str:
        return jsonify({"error": "Parametr 'date' jest wymagany."}), 400

    try:
        query_date = date.fromisoformat(date_str)
    except ValueError:
        return jsonify({"error": "Nieprawidłowy format daty."}), 400

    with session_scope() as db_session:
        sessions = db_session.query(
            TUSSession.id,
            TUSSession.session_time,
            TUSGroup.name,
            TUSTopic.title
        ).join(TUSGroup).join(TUSTopic).filter(TUSSession.session_date == query_date).order_by(
            TUSSession.session_time).all()

        result = [
            {
                "session_id": s.id,
                "session_time": s.session_time.strftime('%H:%M:%S') if s.session_time else None,
                "group_name": s.name,
                "topic_title": s.title
            } for s in sessions
        ]
        return jsonify(result)
        
def check_and_send_journal_reminders():
    """
    Zadanie uruchamiane cyklicznie przez APScheduler.
    Sprawdza, czy terapeuci wypełnili dzienniki dla odbytych sesji i wysyła przypomnienia.
    """
    print("⏳ Uruchomiono zadanie w tle: Sprawdzanie zaległych dzienników...")
    
    # Używamy Twojego kontekstu sesji bazy danych
    with SessionLocal() as db_session:
        try:
            # Przykład: Sprawdzamy sesje z ostatnich 7 dni, które nie mają wpisu w dzienniku.
            # Zakładamy, że sesje indywidualne są w schedule_slots (kind='therapy', status='done' lub minęły).
            # Możesz dostosować to zapytanie do swojej struktury tabel (schedule_slots / dziennik).
            
            # Pobieramy zaległe sesje z ostatnich dni, dla których brak wpisu w tabeli 'dziennik'
            # (dopasowujemy po dacie i terapeucie/kliencie)
            query = text("""
                SELECT DISTINCT s.therapist_id, t.full_name, t.email, (s.starts_at AT TIME ZONE 'Europe/Warsaw')::date as session_date
                FROM schedule_slots s
                JOIN therapists t ON s.therapist_id = t.id
                WHERE s.kind = 'therapy'
                  AND s.status != 'cancelled'
                  AND s.starts_at < NOW()
                  AND s.starts_at >= NOW() - INTERVAL '7 days'
                  AND t.email IS NOT NULL AND t.email != ''
                  AND NOT EXISTS (
                      SELECT 1 FROM dziennik d 
                      WHERE d.therapist_id = s.therapist_id 
                        AND d.data = (s.starts_at AT TIME ZONE 'Europe/Warsaw')::date
                  )
            """)
            
            overdue_sessions = db_session.execute(query).mappings().all()
            
            if not overdue_sessions:
                print("✅ Brak zaległych dzienników do wysyłki.")
                return

            # Grupowanie zaległości per terapeuta, aby wysłać jeden zbiorczy e-mail
            therapist_reminders = {}
            for row in overdue_sessions:
                tid = row['therapist_id']
                if tid not in therapist_reminders:
                    therapist_reminders[tid] = {
                        'name': row['full_name'],
                        'email': row['email'],
                        'dates': []
                    }
                therapist_reminders[tid]['dates'].append(str(row['session_date']))

            # Wysyłka powiadomień
            for tid, info in therapist_reminders.items():
                to_email = info['email']
                therapist_name = info['name']
                dates_str = ", ".join(info['dates'])
                
                subject = "Przypomnienie: Uzupełnij zaległe dzienniki terapii"
                body = f"""
                <html>
                  <body>
                    <h2>Witaj {therapist_name},</h2>
                    <p>W systemie zauważono brak wpisów w dzienniku dla odbytych sesji w następujących dniach:</p>
                    <p><strong>{dates_str}</strong></p>
                    <p>Prosimy o zalogowanie się do systemu i uzupełnienie brakujących dokumentacji.</p>
                    <hr>
                    <p><small>Wiadomość wygenerowana automatycznie przez system Centrum.</small></p>
                  </body>
                </html>
                """
                
                # Wykorzystujemy istniejącą w app.py funkcję wysyłającą e-mail w osobnym wątku
                send_email_async(to_email, subject, body)
                print(f"📤 Wysłano e-przypomnienie o dziennikach do: {to_email}")

        except Exception as e:
            print(f"❌ Błąd podczas sprawdzania zaległych dzienników: {e}")


@app.get("/api/tus/sessions/<int:session_id>/attendance")
def get_attendance(session_id):
    """Pobiera listę uczestników i ich status obecności dla danej sesji."""
    with session_scope() as db_session:
        session = db_session.query(TUSSession).filter_by(id=session_id).first()
        if not session:
            return jsonify({"error": "Sesja nie znaleziona"}), 404

        members = db_session.query(Client.id, Client.full_name) \
            .join(TUSGroupMember) \
            .filter(TUSGroupMember.group_id == session.group_id).order_by(Client.full_name).all()

        attendance_records = db_session.query(TUSSessionAttendance) \
            .filter_by(session_id=session_id).all()

        attendance_map = {rec.client_id: rec.status for rec in attendance_records}

        return jsonify({
            "group_name": session.group.name,
            "members": [{"id": m.id, "full_name": m.full_name} for m in members],
            "attendance": attendance_map
        })


@app.post("/api/tus/sessions/<int:session_id>/attendance")
def save_attendance(session_id):
    """Zapisuje listę obecności dla sesji."""
    data = request.get_json()
    if not isinstance(data, list):
        return jsonify({"error": "Oczekiwano listy obiektów."}), 400

    with session_scope() as db_session:
        # Usuń stare wpisy, aby uniknąć konfliktów
        db_session.query(TUSSessionAttendance).filter_by(session_id=session_id).delete()

        # Dodaj nowe wpisy
        for item in data:
            new_attendance = TUSSessionAttendance(
                session_id=session_id,
                client_id=item['client_id'],
                status=item['status']
            )
            db_session.add(new_attendance)
            # POPRAWKA: Tworzymy czytelny opis
            log_msg = f"Sesja ID: {session_id}, Klient ID: {item['client_id']}, Status: {item['status']}"
            log_activity("TUS_OBECNOSC", log_msg)

    return jsonify({"message": "Obecność zapisana pomyślnie."}), 200


@app.route('/api/daily-attendance', methods=['GET'])
def get_daily_attendance():
    try:
        date = request.args.get('date')
        if not date:
            return jsonify({'error': 'Date parameter is required'}), 400

        with session_scope() as db_session:
            # Pobierz obecność z tabeli individual_session_attendance
            attendance_data = db_session.query(
                IndividualSessionAttendance,
                ScheduleSlot,
                Client
            ).join(
                ScheduleSlot, IndividualSessionAttendance.slot_id == ScheduleSlot.id
            ).join(
                Client, ScheduleSlot.client_id == Client.id
            ).filter(
                func.date(ScheduleSlot.starts_at) == date
            ).all()

            result = []
            for attendance, slot, client in attendance_data:
                result.append({
                    'client_id': client.id,
                    'status': attendance.status,
                    'notes': '',
                    'session_time': slot.starts_at.strftime('%H:%M') if slot.starts_at else '09:00',
                    'service_type': slot.kind,
                    'therapist_id': slot.therapist_id
                })

            return jsonify(result)

    except Exception as e:
        print(f"Błąd w /api/daily-attendance: {str(e)}")
        return jsonify([])


# --- STREAMING_CHUNK: Poprawianie pobierania raportu obecności klienta... ---
@app.get("/api/clients/<int:client_id>/all-attendance")
@login_required
def get_client_all_attendance(client_id):
    """Zwraca kompletny miesięczny raport obecności (TUS + indywidualne) dla klienta."""
    month_str = request.args.get('month')
    if not month_str:
        return jsonify({"error": "Parametr 'month' jest wymagany."}), 400

    try:
        year, month = map(int, month_str.split('-'))
    except ValueError:
        return jsonify({"error": "Nieprawidłowy format miesiąca (oczekiwano YYYY-MM)."}), 400

    current_firma_id = session.get('firma_id', 1)

    try:
        with session_scope() as db_session:
            # 1. Pobierz obecności z sesji TUS (z OUTER JOIN na wypadek braku tematu w sesji)
            tus_records = db_session.query(
                TUSSession.session_date.label("date"),
                TUSSessionAttendance.status.label("attendance_status"),
                TUSGroup.name.label('group_name'),
                TUSTopic.title.label('topic_title')
            ).join(TUSGroup, TUSGroup.id == TUSSession.group_id) \
             .join(TUSSessionAttendance, TUSSessionAttendance.session_id == TUSSession.id) \
             .outerjoin(TUSTopic, TUSTopic.id == TUSSession.topic_id) \
             .filter(
                TUSSessionAttendance.client_id == client_id,
                TUSSession.firma_id == current_firma_id,
                extract('year', TUSSession.session_date) == year,
                extract('month', TUSSession.session_date) == month
            ).all()

            # 2. Pobierz zajęcia indywidualne (z OUTER JOIN: znajduje wizyty nawet jeśli nie kliknięto jeszcze obecności!)
            individual_records = db_session.query(
                ScheduleSlot.starts_at.label("date"),
                ScheduleSlot.status.label("slot_status"),
                IndividualSessionAttendance.status.label("attendance_status"),
                Therapist.full_name.label('therapist_name')
            ).outerjoin(IndividualSessionAttendance, ScheduleSlot.id == IndividualSessionAttendance.slot_id) \
             .outerjoin(Therapist, Therapist.id == ScheduleSlot.therapist_id) \
             .filter(
                ScheduleSlot.client_id == client_id,
                ScheduleSlot.kind == 'therapy',
                ScheduleSlot.firma_id == current_firma_id,
                extract('year', func.timezone('Europe/Warsaw', ScheduleSlot.starts_at)) == year,
                extract('month', func.timezone('Europe/Warsaw', ScheduleSlot.starts_at)) == month
            ).all()

            # 3. Zbudowanie ujednoliconej listy wyników
            all_records = []
            
            for record in tus_records:
                all_records.append({
                    "date": record.date.isoformat() if hasattr(record.date, 'isoformat') else str(record.date),
                    "description": f"Grupa TUS: {record.group_name or 'TUS'}",
                    "details": f"Temat: {record.topic_title or 'Brak tematu'}",
                    "status": record.attendance_status or 'obecny'
                })

            for record in individual_records:
                # Jeśli wpis obecności nie istnieje w osobnej tabeli, bierzemy status ze slotu grafiku:
                effective_status = record.attendance_status
                if not effective_status:
                    if record.slot_status == 'done':
                        effective_status = 'obecny'
                    elif record.slot_status == 'cancelled':
                        effective_status = 'nieobecny'
                    else:
                        effective_status = record.slot_status or 'planned'

                date_iso = record.date.isoformat() if record.date and hasattr(record.date, 'isoformat') else str(record.date)

                all_records.append({
                    "date": date_iso,
                    "description": "Terapia indywidualna",
                    "details": f"Terapeuta: {record.therapist_name or 'Przypisany w grafiku'}",
                    "status": effective_status
                })

            # Sortowanie chronologiczne
            all_records.sort(key=lambda x: x['date'])

            return jsonify(all_records), 200

    except Exception as e:
        print(f"❌ Błąd w get_client_all_attendance: {e}")
        import traceback
        traceback.print_exc()
        return jsonify({"error": str(e)}), 500


@app.get("/api/individual-sessions-for-day")
def get_individual_sessions_for_day():
    """Zwraca listę indywidualnych sesji terapeutycznych dla podanej daty wraz z ich statusem obecności."""
    date_str = request.args.get('date')
    if not date_str:
        return jsonify({"error": "Parametr 'date' jest wymagany."}), 400

    try:
        query_date = date.fromisoformat(date_str)
    except ValueError:
        return jsonify({"error": "Nieprawidłowy format daty."}), 400

    with session_scope() as db_session:
        sessions = db_session.query(
            ScheduleSlot.id.label("slot_id"),
            ScheduleSlot.starts_at,
            Client.full_name.label("client_name"),
            Therapist.full_name.label("therapist_name"),
            IndividualSessionAttendance.status.label("attendance_status")
        ).join(Client, Client.id == ScheduleSlot.client_id) \
            .join(Therapist, Therapist.id == ScheduleSlot.therapist_id) \
            .outerjoin(IndividualSessionAttendance, ScheduleSlot.id == IndividualSessionAttendance.slot_id) \
            .filter(
            func.date(ScheduleSlot.starts_at) == query_date,
            ScheduleSlot.kind == 'therapy'
        ).order_by(ScheduleSlot.starts_at).all()

        result = [
            {
                "slot_id": s.slot_id,
                "starts_at": s.starts_at.isoformat(),
                "client_name": s.client_name,
                "therapist_name": s.therapist_name,
                "attendance_status": s.attendance_status or 'obecny'  # Domyślnie 'obecny', jeśli brak wpisu
            } for s in sessions
        ]
        return jsonify(result)


@app.patch("/api/individual-attendance/<int:slot_id>")
@login_required  # Dodajemy, aby wiedzieć KTO zmienia status (do logów)
def update_individual_attendance(slot_id):
    """Aktualizuje lub tworzy (UPSERT) status obecności dla pojedynczego slotu."""
    data = request.get_json()
    new_status = data.get('status')

    if not new_status:
        return jsonify({"error": "Status jest wymagany."}), 400

    try:
        with session_scope() as db_session:
            # 1. Pobierz dane do logowania (Nazwisko klienta i datę wizyty)
            # Łączymy tabelę slotów z klientami
            slot_info = db_session.query(
                ScheduleSlot.starts_at,
                Client.full_name
            ).join(Client, Client.id == ScheduleSlot.client_id) \
                .filter(ScheduleSlot.id == slot_id).first()

            client_name = slot_info.full_name if slot_info else "Nieznany klient"
            visit_date = slot_info.starts_at.strftime(
                '%Y-%m-%d %H:%M') if slot_info and slot_info.starts_at else "Brak daty"

            # 2. Logika UPSERT (Znajdź lub Stwórz)
            attendance_record = db_session.query(IndividualSessionAttendance).filter_by(slot_id=slot_id).first()

            log_action_desc = ""

            if attendance_record:
                # Jeśli istnieje -> Aktualizuj
                old_status = attendance_record.status
                attendance_record.status = new_status
                log_action_desc = f"Zmiana: {old_status} -> {new_status}"
            else:
                # Jeśli nie istnieje -> Stwórz nowy
                new_attendance = IndividualSessionAttendance(slot_id=slot_id, status=new_status)
                db_session.add(new_attendance)
                log_action_desc = f"Ustawiono: {new_status}"

            # 3. Zapisz Log (W tej samej transakcji)
            log_details = f"{log_action_desc}. Klient: {client_name}. Termin: {visit_date}. (Slot ID: {slot_id})"

            # Wywołanie Twojej funkcji logującej
            try:
                log_activity("ZMIANA_OBECNOSCI_IND", log_details)
            except Exception as log_e:
                print(f"⚠️ Błąd zapisu logu: {log_e}")

        return jsonify({"message": "Status obecności zaktualizowany."}), 200

    except Exception as e:
        print(f"❌ Błąd aktualizacji obecności: {e}")
        import traceback
        traceback.print_exc()
        return jsonify({"error": str(e)}), 500


@app.get("/individual_attendance.html")
def individual_attendance_page():
    # Tutaj można dodać @login_required, jeśli strona ma być chroniona
    return app.send_static_file("individual_attendance.html")


def find_best_match(name_to_find, name_list):
    """Prosta funkcja do znajdowania najlepszego dopasowania na liście nazw."""
    if not name_to_find or not name_list:
        return None

    name_to_find_lower = name_to_find.lower()

    for name in name_list:
        if name.lower() == name_to_find_lower:
            return name
    for name in name_list:
        if name.lower().startswith(name_to_find_lower) or name_to_find_lower.startswith(name.lower()):
            return name

    return None


# --- STREAMING_CHUNK: Definiowanie endpointu analizy obrazu... ---
@app.route('/api/parse-schedule-image', methods=['POST'])
@login_required
def parse_schedule_image():
    print("=== ENDPOINT /api/parse-schedule-image START ===")
    
    # 1. Sprawdź klucz API
    api_key = os.getenv("GOOGLE_AI_API_KEY")
    if not api_key:
        print("❌ BŁĄD: Brak klucza API")
        return jsonify({"success": False, "error": "Brak konfiguracji API Google."}), 500

    try:
        # --- Walidacja pliku ---
        if 'schedule_image' not in request.files:
            return jsonify({"success": False, "error": "Serwer nie otrzymał pliku graficznego."}), 400
        
        file = request.files['schedule_image']
        if file.filename == '':
            return jsonify({"success": False, "error": "Nie wybrano pliku."}), 400

        # --- Sprawdzenie rozmiaru ---
        file.seek(0, os.SEEK_END)
        file_size = file.tell()
        file.seek(0)
        
        MAX_SIZE = 5 * 1024 * 1024  # 5MB
        if file_size > MAX_SIZE:
            return jsonify({
                "success": False, 
                "error": f"Plik jest zbyt duży. Maksymalny rozmiar to 5MB."
            }), 413

        # --- Konwersja obrazu ---
        try:
            from PIL import Image
            import io
            
            # Wczytaj obraz
            image = Image.open(file.stream)
            
            # Konwersja do RGB
            if image.mode in ("RGBA", "P"):
                image = image.convert("RGB")
            
            # Zmniejsz obraz
            max_size = 800
            if image.width > max_size:
                ratio = max_size / image.width
                new_height = int(image.height * ratio)
                image = image.resize((max_size, new_height), Image.Resampling.LANCZOS)
                print(f"📉 Skompresowano obraz do: {max_size}x{new_height}")
            
            # Zapisz jako JPEG
            buffered = io.BytesIO()
            image.save(buffered, format="JPEG", quality=75, optimize=True)
            img_b64 = base64.b64encode(buffered.getvalue()).decode('utf-8')
            
            compressed_size = len(buffered.getvalue()) / (1024 * 1024)
            print(f"📊 Rozmiar po kompresji: {compressed_size:.2f}MB")
            
        except Exception as e:
            print(f"❌ Błąd przetwarzania obrazu: {e}")
            return jsonify({"success": False, "error": f"Błąd przetwarzania obrazu: {str(e)}"}), 400

        # --- Przygotowanie zapytania ---
        scope = request.form.get('scope', 'day')
        input_date = request.form.get('date', '')
        input_month = request.form.get('month', '')
        therapist_name = request.form.get('therapist_name', '')
        
        prompt = f"""
        Przeanalizuj grafik zajęć terapeutycznych.
        Terapeuta: {therapist_name}
        Data: {input_date if scope == 'day' else input_month}
        
        Wypisz listę wizyt w formacie JSON:
        [
          {{
            "date": "YYYY-MM-DD",
            "start_time": "HH:MM",
            "end_time": "HH:MM",
            "client_name": "imię i nazwisko pacjenta",
            "therapist_name": "imię i nazwisko terapeuty",
            "type": "indywidualna lub grupowa"
          }}
        ]
        
        Jeśli nie widzisz żadnych wizyt, zwróć pustą tablicę: []
        """

        # --- WYBIERZ MODEL: gemini-3.5-flash2.0-flash-exp ---
        # Możesz też spróbować: gemini-3.5-flash1.5-pro, gemini-3.5-flash1.5-flash
        MODEL = "gemini-3.5-flash"  # lub "gemini-3.5-flash1.5-pro"
        
        # Użyj starego, sprawdzonego endpointu generateContent
        api_url = f"https://generativelanguage.googleapis.com/v1beta/models/{MODEL}:generateContent?key={api_key}"
        
        payload = {
            "contents": [{
                "parts": [
                    {"text": prompt},
                    {"inline_data": {"mime_type": "image/jpeg", "data": img_b64}}
                ]
            }],
            "generationConfig": {
                "temperature": 0.2,
                "maxOutputTokens": 4096,
                "responseMimeType": "application/json"
            }
        }
        
        try:
            print(f"📡 Wysyłanie zapytania do Google Gemini (model: {MODEL})...")
            
            response = requests.post(
                api_url,
                json=payload,
                headers={'Content-Type': 'application/json'},
                timeout=30
            )
            
            print(f"📥 Status odpowiedzi: {response.status_code}")
            
            if response.status_code != 200:
                print(f"❌ Błąd HTTP: {response.status_code}")
                print(f"Odpowiedź: {response.text[:500]}")
                
                # Jeśli model nie działa, spróbuj z innym
                if response.status_code == 404:
                    # Spróbuj z gemini-3.5-flash1.5-pro jako fallback
                    print("🔄 Próba z modelem gemini-3.5-flash...")
                    MODEL = "gemini-3.5-flash"
                    api_url = f"https://generativelanguage.googleapis.com/v1beta/models/{MODEL}:generateContent?key={api_key}"
                    response = requests.post(api_url, json=payload, timeout=30)
                    
                    if response.status_code == 200:
                        print(f"✅ Sukces z modelem {MODEL}")
                    else:
                        return jsonify({
                            "success": False,
                            "error": "Żaden z dostępnych modeli nie jest dostępny. Spróbuj użyć 'gemini-3.5-flash'."
                        }), 404
                else:
                    return jsonify({
                        "success": False,
                        "error": f"Błąd zewnętrznego systemu AI (Kod: {response.status_code})"
                    }), response.status_code
            
            result_json = response.json()
            
            # Wyciągnij tekst z odpowiedzi
            ai_text = None
            if 'candidates' in result_json and len(result_json['candidates']) > 0:
                candidate = result_json['candidates'][0]
                if 'content' in candidate and 'parts' in candidate['content']:
                    for part in candidate['content']['parts']:
                        if 'text' in part:
                            ai_text = part['text']
                            break
            
            if not ai_text:
                print("❌ Nie znaleziono tekstu w odpowiedzi AI")
                print(f"Odpowiedź: {json.dumps(result_json, indent=2)[:500]}")
                return jsonify({
                    "success": False,
                    "error": "AI nie zwróciło tekstowej odpowiedzi."
                }), 500

            print(f"📝 Odpowiedź AI (pierwsze 300 znaków): {ai_text[:300]}...")

        except requests.exceptions.Timeout:
            print("⏱️ Timeout z Google API")
            return jsonify({
                "success": False,
                "error": "Przekroczono czas oczekiwania na odpowiedź AI."
            }), 408
        except Exception as e:
            print(f"❌ Błąd Gemini API: {e}")
            return jsonify({
                "success": False,
                "error": f"Błąd komunikacji z Google AI: {str(e)}"
            }), 500

        # --- Parsowanie odpowiedzi ---
        try:
            # Usuń znaczniki markdown
            ai_text = ai_text.replace('```json', '').replace('```', '').strip()
            
            # Szukaj JSON
            import re
            json_match = re.search(r'\[\s*\{[\s\S]*\}\s*\]', ai_text)
            
            if not json_match:
                print("❌ Nie znaleziono JSON w odpowiedzi")
                return jsonify({
                    "success": False,
                    "error": "AI nie zwróciło danych w oczekiwanym formacie.",
                    "debug": ai_text[:500]
                }), 422
            
            parsed_data = json.loads(json_match.group())
            
            if isinstance(parsed_data, dict):
                parsed_data = [parsed_data]
            
            # Post-processing
            final_data = []
            for item in parsed_data:
                if not item.get('therapist_name'):
                    item['therapist_name'] = therapist_name
                if scope == 'day' and input_date:
                    item['date'] = input_date
                
                # Standaryzacja czasu
                if item.get('start_time'):
                    item['start_time'] = str(item['start_time']).replace('.', ':')
                if item.get('end_time'):
                    item['end_time'] = str(item['end_time']).replace('.', ':')
                
                item['matched'] = False
                item['is_duplicate'] = False
                final_data.append(item)
            
            print(f"✅ Sukces: Odczytano {len(final_data)} wpisów")
            return jsonify({
                "success": True,
                "total_count": len(final_data),
                "data": final_data
            }), 200
            
        except json.JSONDecodeError as e:
            print(f"❌ Błąd parsowania JSON: {e}")
            print(f"📄 Tekst AI: {ai_text}")
            
            return jsonify({
                "success": False,
                "error": "AI zwróciło dane w nieprawidłowym formacie.",
                "debug": ai_text[:500]
            }), 422

    except Exception as e:
        print(f"❌ KRYTYCZNY BŁĄD: {traceback.format_exc()}")
        return jsonify({
            "success": False,
            "error": f"Wewnętrzny błąd serwera: {str(e)}"
        }), 500

        
@app.get("/api/test-name-matching")
def test_name_matching():
    """Endpoint do testowania dopasowywania nazw - dla diagnostyki"""
    name_to_match = request.args.get('name')

    with session_scope() as db_session:
        all_clients = [c.full_name for c in db_session.query(Client).all()]
        all_groups = [g.name for g in db_session.query(TUSGroup).all()]

    print(f"\n=== TEST DOPASOWYWANIA DLA: '{name_to_match}' ===")

    client_match = find_best_match(name_to_match, all_clients)
    group_match = find_best_match(name_to_match, all_groups)

    # Znajdź wszystkich klientów którzy mogą pasować
    potential_client_matches = []
    for client in all_clients:
        if name_to_match.lower() in client.lower():
            potential_client_matches.append(client)

    return jsonify({
        'input': name_to_match,
        'client_match': client_match,
        'group_match': group_match,
        'potential_matches': potential_client_matches,
        'available_clients': all_clients,
        'available_groups': all_groups
    })


@app.before_request
def list_routes():
    if request.endpoint:
        print(f"Endpoint: {request.endpoint}, Method: {request.method}")


# Lub dodaj specjalny endpoint do wyświetlenia wszystkich routes:
@app.route("/api/routes")
def list_all_routes():
    routes = []
    for rule in app.url_map.iter_rules():
        routes.append({
            'endpoint': rule.endpoint,
            'methods': list(rule.methods),
            'path': str(rule)
        })
    return jsonify(routes)


@app.before_request
def check_file_size():
    if request.method == 'POST' and request.path == '/api/parse-schedule-image':
        # Sprawdź rozmiar content-length
        content_length = request.content_length or 0
        max_size = 10 * 1024 * 1024  # 10MB

        if content_length > max_size:
            return jsonify({'error': 'File too large'}), 413


@app.route('/api/health')
def health_check():
    memory_info = psutil.Process(os.getpid()).memory_info()
    return jsonify({
        'status': 'healthy',
        'memory_usage_mb': memory_info.rss / 1024 / 1024,
        'memory_percent': psutil.virtual_memory().percent
    })


# ===== DODAJ TEN ENDPOINT PRZED OSTATNIĄ LINIĄ =====
@app.post("/api/save-parsed-schedule")
def save_parsed_schedule():
    """Zapisuje dane zaimportowane z OCR/AI z przypisaniem do firma_id podmiotu."""
    print("\n" + "=" * 50)
    print("🚀 ROZPOCZYNAM ZAPIS GRAFIKU (SAFE MODE - MULTI-TENANT FIX)")

    try:
        data = request.get_json()
        if not data:
            return jsonify({"success": False, "error": "Brak danych."}), 400

        current_firma_id = session.get('firma_id', 1)
        print(f"📥 Otrzymano {len(data)} wierszy dla firmy ID: {current_firma_id}")

        saved_count = 0
        errors = []

        with session_scope() as db_session:
            therapists = db_session.query(Therapist).all()
            drivers = db_session.query(Driver).all()
            clients = db_session.query(Client).all()
            groups = db_session.query(TUSGroup).all()

            therapists_map = {t.full_name.lower().strip(): t.id for t in therapists if t.full_name}
            drivers_map = {d.full_name.lower().strip(): d.id for d in drivers if d.full_name}
            clients_map = {c.full_name.lower().strip(): c.id for c in clients if c.full_name}
            groups_map = {g.name.lower().strip(): g.id for g in groups if g.name}

            for i, item in enumerate(data):
                row_desc = f"Wiersz {i + 1} ({item.get('client_name')})"
                try:
                    if not item.get('client_name'):
                        continue

                    try:
                        date_str = item.get('date', '')
                        start_str = str(item.get('start_time', '')).replace('.', ':')
                        end_str = str(item.get('end_time', '')).replace('.', ':')

                        starts_at = datetime.fromisoformat(f"{date_str}T{start_str}:00").replace(tzinfo=TZ)
                        ends_at = datetime.fromisoformat(f"{date_str}T{end_str}:00").replace(tzinfo=TZ)
                    except Exception as e:
                        errors.append(f"{row_desc}: Błąd formatu czasu")
                        continue

                    client_name_raw = str(item.get('client_name') or '').strip()
                    client_name_lower = client_name_raw.lower()
                    client_id = None
                    group_id = None

                    item_type = (item.get('type') or '').lower().strip()

                    if item_type == 'tus':
                        if client_name_lower in groups_map:
                            group_id = groups_map[client_name_lower]
                        else:
                            errors.append(f"{row_desc}: Nieznana grupa TUS")
                            continue
                    else:
                        if client_name_lower in clients_map:
                            client_id = clients_map[client_name_lower]
                        else:
                            new_client = Client(full_name=client_name_raw, active=True, firma_id=current_firma_id)
                            db_session.add(new_client)
                            db_session.flush()
                            client_id = new_client.id
                            clients_map[client_name_lower] = client_id

                    role = (item.get('role') or 'therapist')

                    if role == 'driver':
                        driver_val = item.get('driver_name') or item.get('therapist_name')
                        driver_raw = str(driver_val or '').strip()
                        driver_key = driver_raw.lower()

                        if driver_key not in drivers_map:
                            errors.append(f"{row_desc}: Nieznany kierowca '{driver_raw}'")
                            continue

                        driver_id = drivers_map[driver_key]
                        kind = 'dropoff' if item_type in ['dropoff', 'odwóz', 'odwoz'] else 'pickup'
                        p_from = "Dom" if kind == 'pickup' else "Poradnia"
                        p_to = "Poradnia" if kind == 'pickup' else "Dom"

                        new_slot = ScheduleSlot(
                            client_id=client_id,
                            driver_id=driver_id,
                            kind=kind,
                            starts_at=starts_at,
                            ends_at=ends_at,
                            status='planned',
                            place_from=p_from,
                            place_to=p_to,
                            distance_km=0,
                            group_id=None,
                            firma_id=current_firma_id
                        )
                        db_session.add(new_slot)
                        saved_count += 1

                    else:
                        therapist_val = item.get('therapist_name')
                        therapist_raw = str(therapist_val or '').strip()
                        therapist_key = therapist_raw.lower()

                        if therapist_key not in therapists_map:
                            errors.append(f"{row_desc}: Nieznany terapeuta")
                            continue

                        therapist_id = therapists_map[therapist_key]

                        if item_type == 'tus':
                            new_session = TUSSession(
                                group_id=group_id,
                                topic_id=1,
                                session_date=starts_at.date(),
                                session_time=starts_at.time(),
                                firma_id=current_firma_id
                            )
                            db_session.add(new_session)
                            saved_count += 1
                        else:
                            new_group_id = uuid.uuid4()
                            eg = EventGroup(
                                id=new_group_id,
                                client_id=client_id,
                                label=f"Import: {item.get('type', 'Terapia')}",
                                firma_id=current_firma_id
                            )
                            db_session.add(eg)

                            slot = ScheduleSlot(
                                group_id=new_group_id,
                                client_id=client_id,
                                therapist_id=therapist_id,
                                kind='therapy',
                                starts_at=starts_at,
                                ends_at=ends_at,
                                status='planned',
                                place_to='Poradnia',
                                session_id=str(uuid.uuid4()),
                                firma_id=current_firma_id
                            )
                            db_session.add(slot)
                            db_session.flush()

                            if slot.id:
                                db_session.execute(text(
                                    "INSERT INTO individual_session_attendance (slot_id, status, firma_id) VALUES (:sid, 'obecny', :fid)"),
                                    {"sid": slot.id, "fid": current_firma_id}
                                )
                            saved_count += 1

                except Exception as e:
                    print(f"🔥 BŁĄD WEWNĘTRZNY WIERSZA {i + 1}: {e}")
                    import traceback
                    traceback.print_exc()
                    errors.append(f"Wiersz {i + 1}: Błąd wewnętrzny ({str(e)})")

            # --- POPRAWKA: return znajduje się teraz na prawidłowym poziomie wewnątrz bloku try ---
            return jsonify({
                "success": True,
                "saved_count": saved_count,
                "errors": errors,
                "message": f"Zapisano {saved_count} wpisów."
            })

    except Exception as e:
        print(f"❌ KRYTYCZNY BŁĄD ENDPOINTU: {e}")
        return jsonify({"success": False, "error": str(e)}), 500


@app.route('/api/scheduled-clients', methods=['GET'])
def get_scheduled_clients():
    try:
        date = request.args.get('date')
        if not date:
            return jsonify({'error': 'Date parameter is required'}), 400

        with session_scope() as db_session:
            # Sprawdź czy tabela schedule istnieje
            try:
                # Pobierz klientów z zaplanowanymi zajęciami na daną datę
                scheduled_clients = db_session.query(Client).join(
                    ScheduleSlot, Client.id == ScheduleSlot.client_id
                ).filter(
                    func.date(ScheduleSlot.starts_at) == date,
                    Client.active == True
                ).order_by(Client.full_name).all()

                result = []
                for client in scheduled_clients:
                    # Znajdź slot dla tego klienta w wybranej dacie
                    slot = db_session.query(ScheduleSlot).filter(
                        ScheduleSlot.client_id == client.id,
                        func.date(ScheduleSlot.starts_at) == date
                    ).first()

                    result.append({
                        'client_id': client.id,
                        'full_name': client.full_name,
                        'phone': client.phone,
                        'session_time': slot.starts_at.strftime('%H:%M') if slot else '09:00',
                        'service_type': slot.kind if slot else 'therapy',
                        'therapist_id': slot.therapist_id if slot else 1,
                        'therapist_name': 'Do ustalenia',  # Możesz dodać join do therapists
                        'service_name': 'Zajęcia terapeutyczne'
                    })

                return jsonify(result)

            except Exception as table_error:
                print(f"Tabela schedule nie istnieje, używam wszystkich klientów: {table_error}")

                # Fallback: wszyscy aktywni klienci
                clients = db_session.query(Client).filter(Client.active == True).order_by(Client.full_name).all()

                scheduled_clients = []
                for i, client in enumerate(clients):
                    scheduled_clients.append({
                        'client_id': client.id,
                        'full_name': client.full_name,
                        'phone': client.phone,
                        'session_time': f"{(9 + i % 6):02d}:00",
                        'service_type': 'therapy',
                        'therapist_id': (i % 3) + 1,
                        'therapist_name': ['Anna Kowalska', 'Piotr Nowak', 'Maria Wiśniewska'][i % 3],
                        'service_name': 'Terapia indywidualna'
                    })

                return jsonify(scheduled_clients)

    except Exception as e:
        print(f"Błąd w scheduled-clients: {str(e)}")
        return jsonify({'error': str(e)}), 500


@app.route('/api/attendance/bulk', methods=['POST'])
def save_bulk_attendance():
    try:
        data = request.get_json()
        if not data:
            return jsonify({'error': 'Brak danych JSON'}), 400

        date = data.get('date')
        attendance_list = data.get('attendance', [])

        if not date:
            return jsonify({'error': 'Date is required'}), 400

        print(f"Zapisuję obecność dla daty {date}, liczba wpisów: {len(attendance_list)}")

        saved_count = 0
        with session_scope() as db_session:
            for attendance_data in attendance_list:
                client_id = attendance_data.get('client_id')
                status = attendance_data.get('status')
                session_time = attendance_data.get('session_time', '09:00')
                service_type = attendance_data.get('service_type', 'therapy')
                therapist_id = attendance_data.get('therapist_id', 1)
                notes = attendance_data.get('notes', '')

                if not client_id or not status:
                    continue

                # Znajdź lub utwórz slot dla tego klienta i daty
                slot = db_session.query(ScheduleSlot).filter(
                    ScheduleSlot.client_id == client_id,
                    func.date(ScheduleSlot.starts_at) == date,
                    ScheduleSlot.kind == 'therapy'
                ).first()

                if not slot:
                    # Utwórz nowy slot jeśli nie istnieje
                    starts_at = datetime.strptime(f"{date} {session_time}", "%Y-%m-%d %H:%M").replace(tzinfo=TZ)
                    ends_at = starts_at + timedelta(hours=1)

                    slot = ScheduleSlot(
                        client_id=client_id,
                        therapist_id=therapist_id,
                        kind='therapy',
                        starts_at=starts_at,
                        ends_at=ends_at,
                        status='planned'
                    )
                    db_session.add(slot)
                    db_session.flush()  # Aby uzyskać ID

                # Znajdź lub utwórz wpis obecności
                attendance_record = db_session.query(IndividualSessionAttendance).filter_by(
                    slot_id=slot.id
                ).first()

                if attendance_record:
                    # Aktualizuj istniejący wpis
                    attendance_record.status = status
                else:
                    # Utwórz nowy wpis
                    new_attendance = IndividualSessionAttendance(
                        slot_id=slot.id,
                        status=status
                    )
                    db_session.add(new_attendance)

                saved_count += 1

        return jsonify({
            'message': f'Obecność zapisana pomyślnie',
            'count': saved_count,
            'date': date
        })

    except Exception as e:
        print(f"Błąd w /api/attendance/bulk: {str(e)}")
        import traceback
        print(f"Traceback: {traceback.format_exc()}")
        return jsonify({'error': str(e)}), 500


@app.route('/api/daily-attendance/bulk', methods=['POST'])
def save_daily_attendance_bulk():
    try:
        data = request.get_json()
        if not data:
            return jsonify({'error': 'Brak danych JSON'}), 400

        date = data.get('date')
        attendance_list = data.get('attendance', [])

        if not date:
            return jsonify({'error': 'Date is required'}), 400

        print(f"Zapisuję obecność dla daty {date}, liczba wpisów: {len(attendance_list)}")

        saved_count = 0
        with session_scope() as db_session:
            for attendance_data in attendance_list:
                client_id = attendance_data.get('client_id')
                status = attendance_data.get('status')
                session_time = attendance_data.get('session_time', '09:00')
                service_type = attendance_data.get('service_type', 'therapy')
                therapist_id = attendance_data.get('therapist_id', 1)
                notes = attendance_data.get('notes', '')

                if not client_id or not status:
                    continue

                # Znajdź lub utwórz slot dla tego klienta i daty
                slot = db_session.query(ScheduleSlot).filter(
                    ScheduleSlot.client_id == client_id,
                    func.date(ScheduleSlot.starts_at) == date,
                    ScheduleSlot.kind == 'therapy'
                ).first()

                if not slot:
                    # Utwórz nowy slot jeśli nie istnieje
                    starts_at = datetime.strptime(f"{date} {session_time}", "%Y-%m-%d %H:%M").replace(tzinfo=TZ)
                    ends_at = starts_at + timedelta(hours=1)

                    slot = ScheduleSlot(
                        client_id=client_id,
                        therapist_id=therapist_id,
                        kind='therapy',
                        starts_at=starts_at,
                        ends_at=ends_at,
                        status='planned'
                    )
                    db_session.add(slot)
                    db_session.flush()

                # Znajdź lub utwórz wpis obecności
                attendance_record = db_session.query(IndividualSessionAttendance).filter_by(
                    slot_id=slot.id
                ).first()

                if attendance_record:
                    attendance_record.status = status
                else:
                    new_attendance = IndividualSessionAttendance(
                        slot_id=slot.id,
                        status=status
                    )
                    db_session.add(new_attendance)

                saved_count += 1

        return jsonify({
            'message': f'Obecność zapisana pomyślnie',
            'count': saved_count,
            'date': date
        })

    except Exception as e:
        print(f"Błąd w /api/daily-attendance/bulk: {str(e)}")
        return jsonify({'error': str(e)}), 500


# Funkcja do znalezienia duplikatów endpointów
def find_duplicate_endpoints():
    endpoints = {}
    duplicates = []

    for rule in app.url_map.iter_rules():
        if rule.endpoint in endpoints:
            duplicates.append(rule.endpoint)
        endpoints[rule.endpoint] = str(rule)

    return duplicates

    # Sprawdź duplikaty przy starcie
    duplicates = find_duplicate_endpoints()
    if duplicates:
        print(f"ZNALEZIONO DUPLIKATY ENDPOINTÓW: {duplicates}")
        # Możesz automatycznie wyjść jeśli chcesz
        # sys.exit


# ===== DODAJ TE ENDPOINTY =====

@app.route('/api/attendance', methods=['GET'])
def get_attendance_by_date():
    """Pobiera obecność dla konkretnej daty/klienta z godziną zajęć (ze schedule_slots)"""
    try:
        date = request.args.get('date')
        client_id = request.args.get('client_id', type=int)  # opcjonalny filtr

        if not date:
            return jsonify({'error': 'Date parameter is required'}), 400

        with session_scope() as db_session:
            # Używamy text() dla łatwiejszego manipulowania datami i unikamy ORM dla prostego raportu
            sql = text("""
                SELECT 
                    isa.status,
                    ss.client_id,
                    ss.therapist_id,
                    ss.kind,
                    ss.starts_at,
                    ss.ends_at,
                    eg.label as group_label  -- Nazwa pakietu (jako opis)
                    -- Brak kolumny 'notes' w IndividualSessionAttendance lub ScheduleSlot
                FROM individual_session_attendance isa
                JOIN schedule_slots ss ON isa.slot_id = ss.id
                LEFT JOIN event_groups eg ON eg.id = ss.group_id::uuid
                WHERE DATE(ss.starts_at) = :date
                AND (:client_id IS NULL OR ss.client_id = :client_id)
            """)

            params = {"date": date, "client_id": client_id}

            # Wykonanie zapytania
            attendance_data = db_session.connection().execute(sql, params).mappings().all()

            result = []
            for row in attendance_data:
                # Formatowanie godziny na HH:MM
                session_time = row['starts_at'].strftime('%H:%M') if row['starts_at'] else '09:00'

                # Użycie Group_label jako tematu/notatek (o ile jest)
                notes = row['group_label'] or ''

                result.append({
                    'client_id': row['client_id'],
                    'status': row['status'],
                    'time': session_time,  # Zmieniono 'session_time' na 'time' zgodnie z frontendem
                    'service_type': row['kind'],
                    'therapist_id': row['therapist_id'],
                    'notes': notes
                })

            return jsonify(result), 200

    except Exception as e:
        print(f"Błąd w /api/attendance: {str(e)}")
        import traceback
        traceback.print_exc()
        return jsonify({'error': str(e)}), 500


@app.route('/api/upload/client-photo', methods=['POST'])
@login_required  # Wymagane, aby log_activity wiedziało kto to zrobił
def upload_client_photo():
    if 'photo' not in request.files:
        return jsonify({'error': 'Brak pliku'}), 400

    file = request.files['photo']
    client_name = request.form.get('client_name', 'Nieznany klient')

    # Walidacja rozszerzenia
    allowed_extensions = {'png', 'jpg', 'jpeg', 'gif', 'webp'}
    if not file.filename.lower().endswith(tuple(allowed_extensions)):
        return jsonify({'error': 'Niedozwolony format pliku (tylko obrazy)'}), 400

    try:
        # Generowanie bezpiecznej nazwy
        import os
        import uuid

        ext = os.path.splitext(file.filename)[1].lower()
        original_safe_name = secure_filename(file.filename)
        # Tworzymy unikalną nazwę: UUID + oryginalna nazwa
        filename = f"{uuid.uuid4()}_{original_safe_name}"

        # Ścieżka zapisu
        save_dir = os.path.join('uploads', 'clients')
        os.makedirs(save_dir, exist_ok=True)
        filepath = os.path.join(save_dir, filename)

        # Zapis pliku
        file.save(filepath)

        # URL do zwrotu (ścieżka relatywna dla frontendu)
        # Używamy forward slashes (/) nawet na Windowsie, bo to URL
        photo_url = f"/uploads/clients/{filename}"

        # --- LOGOWANIE AKCJI ---
        log_msg = f"Przesłano zdjęcie profilowe dla: {client_name}. Plik: {filename}"
        try:
            log_activity("UPLOAD_ZDJECIA_KLIENTA", log_msg)
        except Exception as log_e:
            print(f"⚠️ Błąd zapisu logu uploadu: {log_e}")

        return jsonify({'photo_url': photo_url, 'message': 'Zdjęcie zapisane'}), 200

    except Exception as e:
        print(f"❌ Błąd uploadu zdjęcia: {e}")
        import traceback
        traceback.print_exc()
        return jsonify({'error': f'Błąd serwera: {str(e)}'}), 500


def init_foundation_table():
    """Inicjalizacja tabeli foundation w PostgreSQL"""
    with engine.begin() as conn:
        conn.execute(text('''
                CREATE TABLE IF NOT EXISTS foundation (
                    id SERIAL PRIMARY KEY,
                    name TEXT,
                    krs TEXT UNIQUE,
                    nip TEXT,
                    regon TEXT,
                    city TEXT,
                    voivodeship TEXT,
                    street TEXT,
                    building_number TEXT,
                    postal_code TEXT,
                    email TEXT,
                    phone TEXT,
                    board_members TEXT,
                    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
                )
            '''))

        conn.execute(text('''
                CREATE INDEX IF NOT EXISTS idx_foundation_krs 
                ON foundation(krs)
            '''))

    print("✓ Tabela foundation zainicjalizowana")


def init_projects_table():
    """Inicjalizacja tabeli projects w PostgreSQL (jeśli nie istnieje)"""
    with engine.begin() as conn:
        conn.execute(text('''
                CREATE TABLE IF NOT EXISTS projects (
                    id SERIAL PRIMARY KEY,
                    title VARCHAR(255) NOT NULL,
                    description TEXT,
                    start_date DATE,
                    end_date DATE,
                    status VARCHAR(50) DEFAULT 'planowany',
                    budget FLOAT,
                    coordinator VARCHAR(255),
                    partners TEXT,
                    beneficiaries_count INTEGER,
                    photo_url TEXT,
                    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
                )
            '''))

        conn.execute(text('''
                CREATE INDEX IF NOT EXISTS idx_projects_status 
                ON projects(status)
            '''))

        conn.execute(text('''
                CREATE INDEX IF NOT EXISTS idx_projects_dates 
                ON projects(start_date, end_date)
            '''))

    print("✓ Tabela projects zainicjalizowana")


def init_all_tables():
    """Inicjalizacja wszystkich tabel aplikacji"""
    print("\n" + "=" * 60)
    print("INICJALIZACJA TABEL BAZY DANYCH")
    print("=" * 60)

    try:
        # Sprawdź połączenie z bazą
        with engine.begin() as conn:
            result = conn.execute(text("SELECT version()"))
            version = result.scalar()
            print(f"✓ Połączono z PostgreSQL")
            print(f"  {version[:60]}...")

        # Automatyczne tworzenie tabel z modeli SQLAlchemy (w tym 'users')
        Base.metadata.create_all(bind=engine)
        print("✓ Tabele z modeli SQLAlchemy (Base.metadata) zainicjalizowane.")

        # =========================================================
        # --- AUTOMATYCZNA NAPRAWA STRUKTURY BAZY DANYCH ---
        # =========================================================
        try:
            with engine.begin() as conn:
                # 1. Usuwamy uciążliwe reguły dla kierowców i terapeutów
                conn.execute(text("ALTER TABLE schedule_slots DROP CONSTRAINT IF EXISTS no_overlap_driver;"))
                conn.execute(text("ALTER TABLE schedule_slots DROP CONSTRAINT IF EXISTS no_overlap_therapist;"))
                
                # 2. Dodajemy brakujące kolumny do tabeli firma
                conn.execute(text("ALTER TABLE firma ADD COLUMN IF NOT EXISTS adres_dodatkowy_ulica VARCHAR(255);"))
                conn.execute(text("ALTER TABLE firma ADD COLUMN IF NOT EXISTS adres_dodatkowy_numer VARCHAR(50);"))
                conn.execute(text("ALTER TABLE firma ADD COLUMN IF NOT EXISTS adres_dodatkowy_kod VARCHAR(20);"))
                conn.execute(text("ALTER TABLE firma ADD COLUMN IF NOT EXISTS adres_dodatkowy_miasto VARCHAR(100);"))

                # 3. DODANIE KOLUMNY FIRMA_ID DLA MULTI-TENANT (SaaS)
                # Domyślnie przypisujemy wszystko do firmy ID 1
                conn.execute(text("ALTER TABLE users ADD COLUMN IF NOT EXISTS firma_id INTEGER DEFAULT 1;"))
                # Kolumna na wybór widocznych modułów przez użytkownika (pusty = wszystkie widoczne)
                conn.execute(text("ALTER TABLE users ADD COLUMN IF NOT EXISTS visible_modules VARCHAR(500) DEFAULT '';"))
                conn.execute(text("ALTER TABLE clients ADD COLUMN IF NOT EXISTS firma_id INTEGER DEFAULT 1;"))
                conn.execute(text("ALTER TABLE therapists ADD COLUMN IF NOT EXISTS firma_id INTEGER DEFAULT 1;"))
                conn.execute(text("ALTER TABLE drivers ADD COLUMN IF NOT EXISTS firma_id INTEGER DEFAULT 1;"))
                conn.execute(text("ALTER TABLE schedule_slots ADD COLUMN IF NOT EXISTS firma_id INTEGER DEFAULT 1;"))
                conn.execute(text("ALTER TABLE tus_groups ADD COLUMN IF NOT EXISTS firma_id INTEGER DEFAULT 1;"))
                conn.execute(text("ALTER TABLE projects ADD COLUMN IF NOT EXISTS firma_id INTEGER DEFAULT 1;"))
                conn.execute(text("ALTER TABLE dziennik ADD COLUMN IF NOT EXISTS firma_id INTEGER DEFAULT 1;"))

                print("✓ Zaktualizowano schematy tabel (dodano firma_id).")
                
        except Exception as db_err:
            print(f"⚠️ Uwaga przy aktualizacji struktury bazy: {db_err}")
        # =========================================================
        # =========================================================

        # Inicjalizuj dodatkowe tabele/indeksy (jeśli potrzebne)
        init_documents_table()  # Dokumenty klientów
        init_foundation_table()  # Dane fundacji
        init_projects_table()  # Projekty
        init_client_notes_table()
        init_journal_table()  # Dodano brakujące wywołanie
        init_waiting_clients_table()  # Dodano brakujące wywołanie
        init_resolutions_table()
        init_schedule_import_aliases_table()
        # init_absences_table()    # Dodano brakujące wywołanie

        print("=" * 60)
        print("✓ WSZYSTKIE TABELE GOTOWE")
        print("=" * 60 + "\n")

        return True

    except Exception as e:
        print("\n" + "=" * 60)
        print("✗ BŁĄD INICJALIZACJI")
        print("=" * 60)
        print(f"Błąd: {str(e)}")
        import traceback
        print(traceback.format_exc())
        print("=" * 60 + "\n")
        return False


def init_documents_table():
    """Inicjalizacja tabeli dokumentów w PostgreSQL"""
    with engine.begin() as conn:
        conn.execute(text('''
                CREATE TABLE IF NOT EXISTS client_documents (
                    id SERIAL PRIMARY KEY,
                    client_id INTEGER NOT NULL,
                    file_name TEXT NOT NULL,
                    file_path TEXT NOT NULL,
                    file_type TEXT NOT NULL,
                    file_size INTEGER NOT NULL,
                    document_type TEXT,
                    notes TEXT,
                    upload_date TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                    uploaded_by TEXT,
                    FOREIGN KEY (client_id) REFERENCES clients(id) ON DELETE CASCADE
                )
            '''))

        conn.execute(text('''
                CREATE INDEX IF NOT EXISTS idx_client_documents_client_id 
                ON client_documents(client_id)
            '''))

    print("✓ Tabela client_documents zainicjalizowana")


@app.route('/api/clients/<int:client_id>/documents', methods=['POST'])
@login_required  # Wymagane, aby wiedzieć KTO przesyła plik
def upload_client_documents(client_id):
    print(f"\n=== UPLOAD DOCUMENTS START dla klienta {client_id} ===")
    try:
        # 1. Sprawdź czy klient istnieje i POBIERZ JEGO NAZWĘ (do logów)
        client_name = f"ID {client_id}"
        with engine.connect() as conn:
            client_row = conn.execute(
                text('SELECT full_name FROM clients WHERE id = :cid'),
                {"cid": client_id}
            ).mappings().first()

            if not client_row:
                return jsonify({'error': 'Klient nie istnieje'}), 404

            if client_row['full_name']:
                client_name = client_row['full_name']

        # 2. Walidacja requestu
        if 'files' not in request.files:
            print("Brak klucza 'files' w request.files")
            return jsonify({'error': 'Brak plików'}), 400

        files = request.files.getlist('files')
        print(f"Liczba plików: {len(files)}")

        if not files or files[0].filename == '':
            return jsonify({'error': 'Nie wybrano plików'}), 400

        document_type = request.form.get('document_type', 'Inne')
        notes = request.form.get('notes', '')
        # Pobieramy nazwę użytkownika z sesji (dzięki @login_required)
        uploaded_by = session.get('username', 'system')

        uploaded_files = []
        errors = []

        # 3. Pętla po plikach
        for idx, file in enumerate(files):
            print(f"\n--- Przetwarzanie pliku {idx + 1}/{len(files)} ---")
            print(f"Nazwa: {file.filename}")

            if file and allowed_file(file.filename):
                try:
                    file.seek(0, os.SEEK_END)
                    file_size = file.tell()
                    file.seek(0)
                    print(f"Rozmiar: {file_size} bajtów")

                    if file_size > MAX_FILE_SIZE:
                        errors.append(f'{file.filename}: Plik za duży')
                        continue

                    # Zapisz plik fizycznie
                    filepath = get_safe_filepath(client_id, file.filename)
                    file.save(filepath)
                    print(f"Plik zapisany: {filepath}")

                    file_type = mimetypes.guess_type(file.filename)[0] or 'application/octet-stream'
                    print(f"Typ MIME: {file_type}")

                    # KLUCZOWY MOMENT - zapis do bazy
                    print("Rozpoczynam zapis do bazy...")
                    with engine.begin() as conn:
                        result = conn.execute(text('''
                                INSERT INTO client_documents 
                                (client_id, file_name, file_path, file_type, file_size, 
                                 document_type, notes, uploaded_by)
                                VALUES (:cid, :fname, :fpath, :ftype, :fsize, :dtype, :notes, :uby)
                                RETURNING id
                            '''), {
                            "cid": client_id,
                            "fname": file.filename,
                            "fpath": filepath,
                            "ftype": file_type,
                            "fsize": file_size,
                            "dtype": document_type,
                            "notes": notes,
                            "uby": uploaded_by
                        })

                        doc_id = result.scalar()
                        print(f"SUKCES! Dokument zapisany w bazie, ID: {doc_id}")

                        uploaded_files.append({
                            'id': doc_id,
                            'file_name': file.filename,
                            'file_size': file_size
                        })

                        # --- LOGOWANIE AKCJI (Wewnątrz pętli, per plik) ---
                        try:
                            log_msg = f"Przesłano dokument: {file.filename} ({document_type}) dla: {client_name}"
                            # Używamy Twojej funkcji helpera.
                            # Jeśli log_activity używa engine.begin(), to tutaj jest bezpiecznie,
                            # bo jesteśmy już po wykonaniu inserta dokumentu.
                            log_activity("UPLOAD_DOKUMENTU", log_msg)
                        except Exception as log_e:
                            print(f"⚠️ Nie udało się zapisać logu: {log_e}")

                except Exception as e:
                    print(f"BŁĄD dla pliku {file.filename}: {str(e)}")
                    import traceback
                    print(traceback.format_exc())
                    errors.append(f'{file.filename}: {str(e)}')

                    # Usuń plik fizyczny jeśli baza zawiodła
                    if os.path.exists(filepath):
                        try:
                            os.remove(filepath)
                            print(f"Usunięto plik fizyczny: {filepath}")
                        except:
                            pass
            else:
                print(f"Niedozwolony typ pliku: {file.filename}")
                errors.append(f'{file.filename}: Niedozwolony typ')

        print(f"\n=== UPLOAD ZAKOŃCZONY ===")
        print(f"Zapisane pliki: {len(uploaded_files)}")
        print(f"Błędy: {len(errors)}")

        response = {'count': len(uploaded_files), 'uploaded': uploaded_files}
        if errors:
            response['errors'] = errors

        return jsonify(response), 201

    except Exception as e:
        print(f"BŁĄD KRYTYCZNY: {str(e)}")
        import traceback
        print(traceback.format_exc())
        return jsonify({'error': str(e)}), 500


# Upewnij się, że na górze pliku masz te importy:
# from flask import jsonify
# from twoj_plik_z_modelami import Client  <-- dostosuj nazwę pliku, jeśli modele masz osobno


# --- FUNKCJA EKSTRAKCJI (OCR + TEXT) ---
def extract_content_from_file(file_path):
    ext = file_path.split('.')[-1].lower()
    text = ""

    try:
        # 1. Obsługa PDF
        if ext == 'pdf':
            # Krok A: Próbujemy wyciągnąć tekst cyfrowy (szybkie)
            with pdfplumber.open(file_path) as pdf:
                for page in pdf.pages:
                    extracted = page.extract_text()
                    if extracted:
                        text += extracted + "\n"

            # Krok B: Jeśli tekst jest pusty lub bardzo krótki, to pewnie skan -> Używamy OCR
            if len(text.strip()) < 10:
                text = ""  # Resetujemy, żeby nie mieć śmieci
                # Konwertujemy strony PDF na obrazki
                try:
                    images = convert_from_path(file_path)
                    for img in images:
                        # Czytamy tekst z obrazka (OCR)
                        text += pytesseract.image_to_string(img, lang='pol') + "\n"
                except Exception as e:
                    text += f"\n[Błąd OCR PDF: {str(e)} - upewnij się, że poppler-utils jest zainstalowany]"



        # 3. Obsługa Obrazków (JPG, PNG)
        elif ext in ['jpg', 'jpeg', 'png']:
            try:
                text = pytesseract.image_to_string(Image.open(file_path), lang='pol')
            except Exception as e:
                text = f"[Błąd OCR Obrazka: {str(e)}]"

    except Exception as e:
        return f"[Krytyczny błąd odczytu pliku: {str(e)}]"

    return text


@app.route('/api/clients/<int:client_id>/diagnosis', methods=['POST'])
@login_required
def save_client_diagnosis(client_id):
    try:
        with session_scope() as session:
            client = session.query(Client).get(client_id)
            if not client:
                return jsonify({'error': 'Nie znaleziono klienta'}), 404

            # 1. Pobierz dane z formularza
            form_diagnosis = request.form.get('diagnosis', '').strip()
            file = request.files.get('diagnosis_file')

            ai_extracted_text = ""

            # 2. Jeśli jest plik, wyślij do AI
            if file:
                # Zapisz plik na dysku (standardowo)
                filename = secure_filename(file.filename)
                timestamp = int(datetime.now().timestamp())
                unique_filename = f"{client_id}_{timestamp}_{filename}"

                upload_folder = os.path.join(app.root_path, 'static', 'uploads', 'diagnoses')
                os.makedirs(upload_folder, exist_ok=True)

                file_path = os.path.join(upload_folder, unique_filename)

                # Ważne: Zapisz plik, ale też cofnij wskaźnik, żeby przeczytać go do pamięci dla AI
                file.save(file_path)
                file.stream.seek(0)

                client.diagnosis_file_path = f"/static/uploads/diagnoses/{unique_filename}"

                # --- INTEGRACJA Z AI (GEMINI) ---
                api_key = os.getenv("GOOGLE_AI_API_KEY")

                if api_key:
                    try:
                        print(f"🤖 Wysyłam plik diagnozy do AI...")
                        genai.configure(api_key=api_key)
                        model = genai.GenerativeModel('gemini-3.5-flash')  # lub gemini-3.5-flash1.5-flash

                        # Przygotuj plik dla AI
                        file_bytes = file.read()
                        mime_type = file.mimetype or "image/jpeg"

                        # Jeśli to PDF, Gemini obsługuje application/pdf bezpośrednio w content parts
                        # Jeśli obrazek, to image/jpeg|png

                        doc_part = {
                            "mime_type": mime_type,
                            "data": file_bytes
                        }

                        prompt = """
                        Jesteś asystentem medycznym. Przeanalizuj załączony dokument (orzeczenie lub diagnozę).
                        Wyciągnij z niego DOKŁADNIE dwie sekcje informacji i wypisz je w formacie tekstowym:

                        DIAGNOZA:
                        (Tutaj wpisz rozpoznanie, kod ICD-10 jeśli jest, nazwę schorzenia/niepełnosprawności)

                        ZALECENIA:
                        (Tutaj wypisz w punktach zalecenia terapeutyczne, formy terapii, wskazania do pracy)

                        Jeśli dokument jest nieczytelny, napisz: "Nie udało się odczytać treści".
                        Nie dodawaj żadnych wstępów ani zakończeń, tylko samą treść.
                        """

                        response = model.generate_content([prompt, doc_part])
                        ai_extracted_text = response.text.strip()
                        print("✅ AI odczytało diagnozę.")

                    except Exception as ai_e:
                        print(f"⚠️ Błąd AI: {ai_e}")
                        ai_extracted_text = ""  # Nie przerywamy zapisu, po prostu nie będzie tekstu z AI
                else:
                    print("⚠️ Brak klucza API Google - pomijam OCR AI.")

            # 3. Łączenie treści (Formularz + AI)
            final_diagnosis = form_diagnosis

            if ai_extracted_text:
                if final_diagnosis:
                    # Jeśli użytkownik coś wpisał, dopisujemy AI pod spodem
                    final_diagnosis += "\n\n" + ("=" * 20) + "\n" + ai_extracted_text
                else:
                    # Jeśli pole było puste, wstawiamy wynik AI
                    final_diagnosis = ai_extracted_text

            client.diagnosis = final_diagnosis

            # 4. Przygotowanie odpowiedzi
            response_data = {
                'id': client.id,
                'diagnosis': client.diagnosis,
                'diagnosis_file_path': client.diagnosis_file_path
            }

        return jsonify(response_data), 200

    except Exception as e:
        print(f"❌ Błąd zapisu diagnozy: {e}")
        import traceback
        traceback.print_exc()
        return jsonify({'error': f'Błąd serwera: {str(e)}'}), 500


@app.route('/api/clients/diagnoses', methods=['GET'])
@login_required
def get_clients_diagnoses():
    """Zwraca listę diagnoz pacjentów z rygorystyczną izolacją Multi-tenant."""
    try:
        # POBIERAMY ID FIRMY Z SESJI AKTUALNIE ZALOGOWANEGO UŻYTKOWNIKA
        current_firma_id = session.get('firma_id', 1)

        with session_scope() as db_session:
            # POPRAWKA: Dodano filtr .filter(Client.firma_id == current_firma_id)
            statement = select(Client).filter(Client.firma_id == current_firma_id)
            clients = db_session.execute(statement).scalars().all()

            clients_data = []
            for client in clients:
                clients_data.append({
                    'id': client.id,
                    'full_name': client.full_name,
                    'diagnosis': client.diagnosis if client.diagnosis else "",
                    'diagnosis_file_path': client.diagnosis_file_path
                })

            return jsonify(clients_data), 200

    except Exception as e:
        print(f"❌ Błąd serwera w get_clients_diagnoses: {e}")
        import traceback
        traceback.print_exc()
        return jsonify({'error': f'Błąd serwera: {str(e)}'}), 500

    except Exception as e:
        # Lepsze logowanie błędów
        print(f"Błąd serwera w get_clients_diagnoses: {e}")
        import traceback
        traceback.print_exc()
        return jsonify({'error': f'Błąd serwera: {str(e)}'}), 500


@app.route('/api/clients/<int:client_id>/documents', methods=['GET'])
def get_client_documents(client_id):
    """Pobiera listę dokumentów klienta"""
    print(f"=== GET DOCUMENTS dla klienta {client_id} ===")
    try:
        with engine.begin() as conn:
            # Sprawdź czy klient istnieje
            exists = conn.execute(
                text('SELECT 1 FROM clients WHERE id = :cid'),
                {"cid": client_id}
            ).scalar()

            if not exists:
                print(f"Klient {client_id} nie istnieje")
                return jsonify({'error': 'Klient nie istnieje'}), 404

            # Pobierz dokumenty
            result = conn.execute(text('''
                    SELECT id, client_id, file_name, file_type, file_size,
                           document_type, notes, upload_date, uploaded_by
                    FROM client_documents
                    WHERE client_id = :cid
                    ORDER BY upload_date DESC
                '''), {"cid": client_id})

            documents = [dict(row) for row in result.mappings().all()]
            print(f"Znaleziono {len(documents)} dokumentów")
            return jsonify(documents), 200

    except Exception as e:
        print(f"Błąd: {str(e)}")
        import traceback
        print(traceback.format_exc())
        return jsonify({'error': str(e)}), 500


@app.route('/api/documents/<int:doc_id>/download', methods=['GET'])
@login_required  # Wymagane logowanie do pobrania plików
def download_document(doc_id):
    print(f"\n=== DOWNLOAD DOCUMENT ID: {doc_id} ===")
    try:
        with engine.begin() as conn:
            result = conn.execute(text('''
                    SELECT file_name, file_path, file_type
                    FROM client_documents WHERE id = :did
                '''), {"did": doc_id})

            row = result.mappings().first()

            if not row:
                return jsonify({'error': 'Dokument nie istnieje w bazie'}), 404

            # Normalizacja ścieżki (ważne na Windows/Linux)
            file_path = os.path.normpath(row['file_path'])
            print(f"Ścieżka na dysku: {file_path}")

            if not os.path.exists(file_path):
                return jsonify({'error': 'Fizyczny plik nie został znaleziony na serwerze'}), 404

            # --- LOGOWANIE POBRANIA ---
            try:
                log_activity("POBRANIE_DOKUMENTU", f"Pobrano plik: {row['file_name']} (ID: {doc_id})")
            except Exception as log_e:
                print(f"⚠️ Błąd logowania pobrania: {log_e}")

            # Użyj send_file z Flask
            from flask import send_file as flask_send_file
            return flask_send_file(
                file_path,
                mimetype=row['file_type'],
                as_attachment=True,
                download_name=row['file_name']
            )

    except Exception as e:
        print(f"Błąd pobierania: {str(e)}")
        import traceback
        print(traceback.format_exc())
        return jsonify({'error': str(e)}), 500


@app.route('/api/documents/<int:doc_id>', methods=['DELETE'])
@login_required  # Wymagane logowanie do usuwania
def delete_document(doc_id):
    try:
        with engine.begin() as conn:
            # 1. Pobierz ścieżkę i nazwę PRZED usunięciem
            result = conn.execute(
                text('SELECT file_path, file_name FROM client_documents WHERE id = :did'),
                {"did": doc_id}
            )
            row = result.mappings().first()

            if not row:
                return jsonify({'error': 'Dokument nie istnieje'}), 404

            file_path = row['file_path']
            file_name = row['file_name']

            # 2. Usuń fizyczny plik (jeśli istnieje)
            if file_path and os.path.exists(file_path):
                try:
                    os.remove(file_path)
                    print(f"Usunięto plik z dysku: {file_path}")
                except OSError as e:
                    print(f"⚠️ Błąd usuwania pliku z dysku (ale usuwam z bazy): {e}")

            # 3. Usuń rekord z bazy
            conn.execute(
                text('DELETE FROM client_documents WHERE id = :did'),
                {"did": doc_id}
            )

            # 4. Logowanie
            log_activity("USUNIECIE_DOKUMENTU", f"Usunięto plik: {file_name} (ID: {doc_id})")

            return jsonify({'message': 'Dokument usunięty'}), 200

    except Exception as e:
        print(f"Błąd usuwania dokumentu: {e}")
        return jsonify({'error': str(e)}), 500


# === PROJECTS API ===
@app.route('/api/projects', methods=['GET'])
@login_required
def get_projects():
    status_filter = request.args.get('status')
    current_firma_id = session.get('firma_id', 1)
    with engine.begin() as conn:
        sql = text("""
            SELECT id, title, description, start_date, end_date, status, budget, coordinator, partners, beneficiaries_count, photo_url, created_at, updated_at
            FROM projects WHERE firma_id = :fid AND (:status IS NULL OR status = :status) ORDER BY start_date DESC NULLS LAST
        """)
        result = conn.execute(sql, {"status": status_filter, "fid": current_firma_id}).mappings().all()
        projects = []
        for row in result:
            p = dict(row)
            for f in ['start_date', 'end_date', 'created_at', 'updated_at']:
                if p[f]: p[f] = p[f].isoformat()
            projects.append(p)
        return jsonify(projects), 200

@app.route('/api/projects', methods=['POST'])
@login_required
def create_project():
    data = request.get_json(silent=True) or {}
    if not data.get('title'): return jsonify({'error': 'Tytuł jest wymagany'}), 400
    current_firma_id = session.get('firma_id', 1)
    try:
        with engine.begin() as conn:
            result = conn.execute(text("""
                INSERT INTO projects (title, description, start_date, end_date, status, budget, coordinator, partners, beneficiaries_count, photo_url, firma_id)
                VALUES (:title, :desc, :start, :end, :status, :budget, :coord, :partners, :benef, :photo, :fid) RETURNING id
            """), {
                "title": data['title'], "desc": data.get('description'), "start": data.get('start_date'), "end": data.get('end_date'),
                "status": data.get('status', 'planowany'), "budget": data.get('budget'), "coord": data.get('coordinator'),
                "partners": data.get('partners'), "benef": data.get('beneficiaries_count'), "photo": data.get('photo_url'), "fid": current_firma_id
            })
            new_id = result.scalar()
            log_activity("UTWORZENIE_PROJEKTU", f"Projekt ID: {new_id} w firmie {current_firma_id}")
            return jsonify({'id': new_id, 'message': 'Projekt utworzony'}), 201
    except Exception as e:
        return jsonify({'error': str(e)}), 500

@app.route('/api/projects/<int:project_id>', methods=['PUT'])
@login_required
def update_project(project_id):
    data = request.get_json(silent=True) or {}
    current_firma_id = session.get('firma_id', 1)
    try:
        with engine.begin() as conn:
            result = conn.execute(text("""
                UPDATE projects SET title=:title, description=:desc, start_date=:start, end_date=:end, status=:status,
                                    budget=:budget, coordinator=:coord, partners=:partners, beneficiaries_count=:benef, photo_url=:photo, updated_at=NOW()
                WHERE id = :pid AND firma_id = :fid RETURNING id
            """), {
                "pid": project_id, "title": data['title'], "desc": data.get('description'), "start": data.get('start_date'), "end": data.get('end_date'),
                "status": data.get('status', 'planowany'), "budget": data.get('budget'), "coord": data.get('coordinator'),
                "partners": data.get('partners'), "benef": data.get('beneficiaries_count'), "photo": data.get('photo_url'), "fid": current_firma_id
            })
            if not result.rowcount: return jsonify({'error': 'Projekt nie znaleziony lub brak uprawnień'}), 404
            return jsonify({'message': 'Projekt zaktualizowany'}), 200
    except Exception as e:
        return jsonify({'error': str(e)}), 500


def init_schedule_import_aliases_table():
    """Inicjalizacja tabeli do 'uczenia się' aliasów importu"""
    with engine.begin() as conn:
        conn.execute(text('''
            CREATE TABLE IF NOT EXISTS schedule_import_aliases (
                id SERIAL PRIMARY KEY,
                original_name TEXT NOT NULL, 
                corrected_name TEXT NOT NULL,
                entity_type TEXT NOT NULL CHECK (entity_type IN ('client', 'group')),
                confidence INTEGER NOT NULL DEFAULT 1,
                created_at TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP,
                updated_at TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP,
                CONSTRAINT uq_alias UNIQUE(original_name, entity_type)
            )
        '''))

        conn.execute(text('''
            CREATE INDEX IF NOT EXISTS idx_aliases_corrected_name
            ON schedule_import_aliases(corrected_name);
        '''))

    print("✓ Tabela schedule_import_aliases zainicjalizowana")


@app.route('/api/projects/<int:project_id>', methods=['DELETE'])
@login_required
def delete_project(project_id):
    """Usuwanie projektu"""
    try:
        with engine.begin() as conn:
            # Usuwamy i od razu pobieramy tytuł usuniętego projektu (dla logów)
            sql = text("DELETE FROM projects WHERE id = :pid RETURNING title")
            result = conn.execute(sql, {"pid": project_id})

            row = result.mappings().first()

            if not row:
                return jsonify({'error': 'Projekt nie znaleziony'}), 404

            deleted_title = row['title']

            # --- LOGOWANIE ---
            try:
                log_activity("USUNIECIE_PROJEKTU", f"Usunięto projekt: '{deleted_title}' (ID: {project_id})")
            except Exception as log_e:
                print(f"⚠️ Błąd logowania: {log_e}")

        return jsonify({'message': 'Projekt usunięty'}), 200

    except Exception as e:
        print(f"Błąd usuwania projektu: {e}")
        # Jeśli projekt jest powiązany z innymi tabelami (np. faktury/kllienci), baza rzuci błąd IntegrityError
        return jsonify({'error': str(e)}), 500


@app.get("/api/projects/report")
@login_required
def get_projects_report():
    """Generuje raport merytoryczny projektów z filtrem multi-tenant."""
    year = request.args.get("year", type=int) or datetime.now().year
    current_firma_id = session.get('firma_id', 1)

    with engine.begin() as conn:
        sql = text("""
            SELECT id, title, description, status, start_date, end_date, budget, coordinator, partners, beneficiaries_count
            FROM projects
            WHERE firma_id = :fid AND (EXTRACT(YEAR FROM start_date) = :year OR EXTRACT(YEAR FROM end_date) = :year)
            ORDER BY start_date, title
        """)
        rows = conn.execute(sql, {"year": year, "fid": current_firma_id}).mappings().all()
        
        projects = [dict(p) for p in rows]
        for p in projects:
            if p['start_date']: p['start_date'] = p['start_date'].isoformat()
            if p['end_date']: p['end_date'] = p['end_date'].isoformat()

        return jsonify({
            "year": year,
            "summary": {
                "total_projects": len(projects),
                "completed_projects": sum(1 for p in projects if p['status'] == 'zakończony'),
                "total_beneficiaries": sum(p['beneficiaries_count'] or 0 for p in projects),
                "total_budget": sum(float(p['budget'] or 0) for p in projects)
            },
            "projects": projects
        })


def fetch_krs_data(krs_number):
    """
        Pobieranie danych z KRS przez API
        Używa publicznego API MS (api.stat.gov.pl) lub rejestr.io
        """
    try:
        # Próba 1: API MS (Ministerstwo Sprawiedliwości)
        # Uwaga: To jest przykładowy endpoint - w praktyce trzeba użyć prawdziwego API
        url = f"https://api-krs.ms.gov.pl/api/krs/OdpisAktualny/{krs_number}"

        headers = {
            'Accept': 'application/json'
        }

        response = requests.get(url, headers=headers, timeout=10)

        if response.status_code == 200:
            data = response.json()
            return parse_krs_response(data)

        # Próba 2: Alternatywne API (rejestr.io)
        url_alt = f"https://rejestr.io/api/v1/krs/{krs_number}"
        response_alt = requests.get(url_alt, timeout=10)

        if response_alt.status_code == 200:
            data_alt = response_alt.json()
            return parse_rejestr_io_response(data_alt)

        return None

    except Exception as e:
        print(f"Błąd pobierania danych KRS: {e}")
        return None


def parse_krs_response(data):
    """
    Zaawansowane parsowanie odpowiedzi z oficjalnego API KRS (MS).
    Obsługuje różne struktury JSON dla Zarządu.
    """
    try:
        odpis = data.get('odpis', {})
        dane = odpis.get('dane', {})

        foundation_data = {
            'name': dane.get('dzial1', {}).get('danePodmiotu', {}).get('nazwa', ''),
            'krs': odpis.get('naglowekA', {}).get('numerKRS', ''),
            'nip': dane.get('dzial1', {}).get('danePodmiotu', {}).get('identyfikatory', {}).get('nip', ''),
            'regon': dane.get('dzial1', {}).get('danePodmiotu', {}).get('identyfikatory', {}).get('regon', ''),
        }

        # --- Adres siedziby ---
        adres = dane.get('dzial1', {}).get('siedzibaIAdres', {}).get('adres', {})
        foundation_data['city'] = adres.get('miejscowosc', '')
        foundation_data['street'] = adres.get('ulica', '')
        foundation_data['building_number'] = adres.get('nrDomu', '')
        foundation_data['apartment_number'] = adres.get('nrLokalu', '')
        foundation_data['postal_code'] = adres.get('kodPocztowy', '')
        foundation_data['voivodeship'] = adres.get('wojewodztwo', '')
        foundation_data['county'] = adres.get('powiat', '')
        foundation_data['municipality'] = adres.get('gmina', '')

        # --- Zarząd (Parsowanie skomplikowanej struktury) ---
        board_members = []
        dzial2 = dane.get('dzial2', {})

        # Szukamy sekcji reprezentacji (różne nazwy w zależności od typu podmiotu)
        organ_reprezentacji = dzial2.get('organUprawnionyDoReprezentacji', {})
        if not organ_reprezentacji:
            # Czasami jest to organ nadzoru, jeśli brak reprezentacji wprost
            organ_reprezentacji = dzial2.get('organNadzoru', {})

        sklad = organ_reprezentacji.get('sklad', [])

        for member in sklad:
            # Imię i nazwisko często są w zagnieżdżonych obiektach
            nazwisko_obj = member.get('nazwisko', {})
            imiona_obj = member.get('imiona', {})

            nazwisko = nazwisko_obj.get('nazwiskoI', '')
            imie = imiona_obj.get('imie', '')

            # Funkcja w organie
            funkcja = member.get('funkcjaWOrganie', '')

            # Jeśli dane są bezpośrednio (niektóre wersje API)
            if not nazwisko and 'nazwisko' in member and isinstance(member['nazwisko'], str):
                nazwisko = member['nazwisko']
            if not imie and 'imiona' in member and isinstance(member['imiona'], str):
                imie = member['imiona']

            # Składamy string
            full_name = f"{imie} {nazwisko}".strip()
            if full_name:
                # Format: Imię Nazwisko - Funkcja
                entry = f"{full_name}"
                if funkcja:
                    entry += f" - {funkcja}"
                board_members.append(entry)

        # Zapisujemy jako string oddzielony nowymi liniami dla bazy danych
        foundation_data['board_members'] = '\n'.join(board_members)

        return foundation_data

    except Exception as e:
        print(f"Błąd parsowania danych KRS: {e}")
        import traceback
        traceback.print_exc()
        return None


def parse_rejestr_io_response(data):
    """Parsowanie odpowiedzi z alternatywnego API rejestr.io"""
    try:
        foundation_data = {
            'name': data.get('nazwa', ''),
            'krs': data.get('krs', ''),
            'nip': data.get('nip', ''),
            'regon': data.get('regon', ''),
            'city': data.get('adres', {}).get('miejscowosc', ''),
            'voivodeship': data.get('adres', {}).get('wojewodztwo', ''),
            'street': data.get('adres', {}).get('ulica', ''),
            'building_number': data.get('adres', {}).get('nr_domu', ''),
            'postal_code': data.get('adres', {}).get('kod_pocztowy', ''),
        }

        # Zarząd
        board_members = []
        for member in data.get('reprezentacja', []):
            name = member.get('imie_nazwisko', '')
            function = member.get('funkcja', '')
            if name:
                board_members.append(f"{name} - {function}")
        foundation_data['board_members'] = '\n'.join(board_members)

        return foundation_data

    except Exception as e:
        print(f"Błąd parsowania danych z rejestr.io: {e}")
        return None


'''@app.route('/api/foundation/fetch-krs', methods=['POST'])
@app.route('/api/foundation', methods=['GET'])
def get_foundation():
    """Pobierz dane fundacji z bazy"""
    try:
        with engine.begin() as conn:
            result = conn.execute(
                text('SELECT * FROM foundation ORDER BY updated_at DESC LIMIT 1')
            )
            row = result.mappings().first()

        if row:
            return jsonify(dict(row)), 200
        else:
            return jsonify({}), 200

    except Exception as e:
        return jsonify({'error': f'Błąd serwera: {str(e)}'}), 500'''

@app.route('/api/foundation', methods=['GET'])
@login_required
def get_foundation_correct():
    """Pobiera dane adresowe bieżącej fundacji na potrzeby interfejsu."""
    current_firma_id = session.get('firma_id', 1)
    try:
        with engine.begin() as conn:
            row = conn.execute(text("SELECT * FROM firma WHERE id = :fid"), {"fid": current_firma_id}).mappings().first()
        if row:
            return jsonify({
                "street": row.get('adres_dodatkowy_ulica') or row.get('ulica'),
                "building_number": row.get('adres_dodatkowy_numer') or row.get('numer_budynku'),
                "postal_code": row.get('adres_dodatkowy_kod') or row.get('kod_pocztowy'),
                "city": row.get('adres_dodatkowy_miasto') or row.get('miasto')
            }), 200
        return jsonify({}), 200
    except Exception as e:
        return jsonify({'error': str(e)}), 500


@app.route('/api/foundation', methods=['POST'])
def save_foundation():
    """Zapisz/aktualizuj dane fundacji"""
    try:
        data = request.get_json()

        with engine.begin() as conn:
            conn.execute(text('''
                    INSERT INTO foundation 
                    (name, krs, nip, regon, city, voivodeship, street, building_number,
                     postal_code, email, phone, board_members, updated_at)
                    VALUES (:name, :krs, :nip, :regon, :city, :voiv, :street, :building,
                            :postal, :email, :phone, :board, :updated)
                    ON CONFLICT (krs) 
                    DO UPDATE SET 
                        name = EXCLUDED.name,
                        nip = EXCLUDED.nip,
                        regon = EXCLUDED.regon,
                        city = EXCLUDED.city,
                        voivodeship = EXCLUDED.voivodeship,
                        street = EXCLUDED.street,
                        building_number = EXCLUDED.building_number,
                        postal_code = EXCLUDED.postal_code,
                        email = EXCLUDED.email,
                        phone = EXCLUDED.phone,
                        board_members = EXCLUDED.board_members,
                        updated_at = EXCLUDED.updated_at
                '''), {
                'name': data.get('name'),
                'krs': data.get('krs'),
                'nip': data.get('nip'),
                'regon': data.get('regon'),
                'city': data.get('city'),
                'voiv': data.get('voivodeship'),
                'street': data.get('street'),
                'building': data.get('building_number'),
                'postal': data.get('postal_code'),
                'email': data.get('email'),
                'phone': data.get('phone'),
                'board': data.get('board_members'),
                'updated': datetime.now()
            })

        return jsonify({'message': 'Dane fundacji zapisane pomyślnie'}), 200

    except Exception as e:
        return jsonify({'error': f'Błąd serwera: {str(e)}'}), 500


@app.route('/api/debug/schedule_structure', methods=['GET'])
def check_schedule_structure():
    """Sprawdź strukturę schedule_slots - z konwersją typów PG"""
    conn = None
    cur = None

    try:
        conn = psycopg2.connect(
            host='localhost',
            database='suo',  # ZMIEŃ
            user='postgres',  # ZMIEŃ
            password='EDUQ'  # ZMIEŃ
        )
        cur = conn.cursor(cursor_factory=RealDictCursor)

        # Pobierz kolumny
        cur.execute("""
                SELECT column_name, data_type 
                FROM information_schema.columns 
                WHERE table_name = 'schedule_slots'
                ORDER BY ordinal_position
            """)
        columns = [dict(c) for c in cur.fetchall()]

        # Pobierz przykładowe dane BEZ kolumn typu range
        cur.execute("""
                SELECT 
                    id, client_id, kind, therapist_id, driver_id, 
                    vehicle_id, 
                    starts_at::text as starts_at,  -- konwersja na text
                    ends_at::text as ends_at,      -- konwersja na text
                    place_from, place_to, status,
                    CASE WHEN group_id IS NOT NULL THEN group_id ELSE NULL END as group_id
                FROM schedule_slots 
                ORDER BY id DESC
                LIMIT 5
            """)
        samples = [dict(s) for s in cur.fetchall()]

        return jsonify({
            "status": "ok",
            "columns": columns,
            "sample_data": samples
        })

    except Exception as e:
        import traceback
        return jsonify({
            "status": "error",
            "error": str(e),
            "traceback": traceback.format_exc()
        }), 200

    finally:
        if cur:
            cur.close()
        if conn:
            conn.close()


@app.route('/api/schedule/check-conflicts', methods=['POST'])
def check_schedule_conflicts():
    """Sprawdza kolizje dla edytowanego pakietu (Pozwala na stykające się terminy)"""
    data = request.get_json()

    group_id = data.get('group_id')  # UUID pakietu (jeśli edycja)
    client_id = data.get('client_id')
    therapy = data.get('therapy')
    pickup = data.get('pickup')
    dropoff = data.get('dropoff')

    conn = None
    cur = None
    conflicts = {
        "therapy": [],
        "pickup": [],
        "dropoff": [],
        "client": [],
        "total": 0
    }

    try:
        conn = psycopg2.connect(
            host='localhost',
            port='5432',
            database='suo',  # ZMIEŃ JEŚLI TRZEBA
            user='postgres', # ZMIEŃ JEŚLI TRZEBA
            password='EDUQ'  # ZMIEŃ JEŚLI TRZEBA
        )
        cur = conn.cursor(cursor_factory=RealDictCursor)

        # SPRAWDŹ KOLIZJE TERAPEUTY
        if therapy:
            therapist_id = therapy.get('therapist_id')
            starts_at = therapy.get('starts_at')
            ends_at = therapy.get('ends_at')

            cur.execute("""
                    SELECT 
                        ss.id,
                        ss.group_id::text,
                        c.full_name as client_name,
                        ss.starts_at,
                        ss.ends_at,
                        'Terapeuta już zajęty' as reason
                    FROM schedule_slots ss
                    JOIN clients c ON ss.client_id = c.id
                    WHERE ss.therapist_id = %s
                    AND ss.status NOT IN ('cancelled')
                    -- Zmieniono OVERLAPS na klasyczny warunek bez "=" (pozwala na styk)
                    AND (ss.starts_at < %s::timestamptz AND ss.ends_at > %s::timestamptz)
                    AND (
                        %s IS NULL OR ss.group_id::text != %s
                    )
                    ORDER BY ss.starts_at
                """, (therapist_id, ends_at, starts_at, group_id, group_id))

            therapy_conflicts = cur.fetchall()
            conflicts["therapy"] = [dict(row) for row in therapy_conflicts]

        # SPRAWDŹ KOLIZJE KIEROWCY (PICKUP)
        if pickup:
            driver_id = pickup.get('driver_id')
            starts_at = pickup.get('starts_at')
            ends_at = pickup.get('ends_at')

            if driver_id:
                cur.execute("""
                        SELECT 
                            ss.id,
                            ss.group_id::text,
                            c.full_name as client_name,
                            ss.starts_at,
                            ss.ends_at,
                            ss.kind,
                            'Kierowca już zajęty' as reason
                        FROM schedule_slots ss
                        JOIN clients c ON ss.client_id = c.id
                        WHERE ss.driver_id = %s
                        AND ss.kind IN ('pickup', 'dropoff')
                        AND ss.status NOT IN ('cancelled')
                        AND (ss.starts_at < %s::timestamptz AND ss.ends_at > %s::timestamptz)
                        AND (
                            %s IS NULL OR ss.group_id::text != %s
                        )
                        ORDER BY ss.starts_at
                    """, (driver_id, ends_at, starts_at, group_id, group_id))

                pickup_conflicts = cur.fetchall()
                conflicts["pickup"] = [dict(row) for row in pickup_conflicts]

        # SPRAWDŹ KOLIZJE KIEROWCY (DROPOFF)
        if dropoff:
            driver_id = dropoff.get('driver_id')
            starts_at = dropoff.get('starts_at')
            ends_at = dropoff.get('ends_at')

            if driver_id:
                cur.execute("""
                        SELECT 
                            ss.id,
                            ss.group_id::text,
                            c.full_name as client_name,
                            ss.starts_at,
                            ss.ends_at,
                            ss.kind,
                            'Kierowca już zajęty' as reason
                        FROM schedule_slots ss
                        JOIN clients c ON ss.client_id = c.id
                        WHERE ss.driver_id = %s
                        AND ss.kind IN ('pickup', 'dropoff')
                        AND ss.status NOT IN ('cancelled')
                        AND (ss.starts_at < %s::timestamptz AND ss.ends_at > %s::timestamptz)
                        AND (
                            %s IS NULL OR ss.group_id::text != %s
                        )
                        ORDER BY ss.starts_at
                    """, (driver_id, ends_at, starts_at, group_id, group_id))

                dropoff_conflicts = cur.fetchall()
                conflicts["dropoff"] = [dict(row) for row in dropoff_conflicts]

        # SPRAWDŹ KOLIZJE KLIENTA (czy klient nie ma już czegoś w tym czasie)
        if client_id and therapy:
            starts_at = therapy.get('starts_at')
            ends_at = therapy.get('ends_at')

            cur.execute("""
                    SELECT 
                        ss.id,
                        ss.group_id::text,
                        ss.kind,
                        ss.starts_at,
                        ss.ends_at,
                        t.full_name as therapist_name,
                        'Klient ma już inne zajęcia' as reason
                    FROM schedule_slots ss
                    LEFT JOIN therapists t ON ss.therapist_id = t.id
                    WHERE ss.client_id = %s
                    AND ss.status NOT IN ('cancelled')
                    AND (ss.starts_at < %s::timestamptz AND ss.ends_at > %s::timestamptz)
                    AND (
                        %s IS NULL OR ss.group_id::text != %s
                    )
                    ORDER BY ss.starts_at
                """, (client_id, ends_at, starts_at, group_id, group_id))

            client_conflicts = cur.fetchall()
            conflicts["client"] = [dict(row) for row in client_conflicts]

        # POLICZ WSZYSTKIE KONFLIKTY
        conflicts["total"] = (
                len(conflicts["therapy"]) +
                len(conflicts["pickup"]) +
                len(conflicts["dropoff"]) +
                len(conflicts["client"])
        )

        return jsonify(conflicts)

    except Exception as e:
        print(f"BŁĄD w check_schedule_conflicts: {e}")
        import traceback
        traceback.print_exc()
        return jsonify({"error": str(e)}), 500

    finally:
        if cur:
            cur.close()
        if conn:
            conn.close()

 # ==========================================
# 2. ENDPOINTY DLA ASYSTENTA GŁOSOWEGO
# ==========================================



@app.route('/api/drivers/<int:driver_id>/schedule', methods=['GET'])
@login_required
def get_driver_schedule(driver_id):
    """
    Harmonogram tras kierowcy. Korzysta z globalnego engine bazy danych chmury (SaaS production ready).
    """
    month_str = request.args.get('month')
    current_firma_id = session.get('firma_id', 1)

    try:
        # Korzystamy z globalnego silnika, który zna prawidłowy adres bazy na Renderze
        with engine.connect() as conn:
            # Zamieniliśmy %s na bezpieczne nazwane parametry SQLAlchemy (:did, :fid)
            query = """
                SELECT 
                    ss.id as slot_id,
                    ss.group_id::text as group_id,
                    ss.driver_id,
                    ss.client_id,
                    c.full_name as client_name,
                    to_char(ss.starts_at AT TIME ZONE 'Europe/Warsaw', 'YYYY-MM-DD"T"HH24:MI:SS') as starts_at,
                    to_char(ss.ends_at   AT TIME ZONE 'Europe/Warsaw', 'YYYY-MM-DD"T"HH24:MI:SS') as ends_at,
                    ss.kind,
                    ss.status,
                    ss.place_from,
                    ss.place_to,
                    ss.distance_km,
                    ss.vehicle_id
                FROM schedule_slots ss
                LEFT JOIN clients c ON ss.client_id = c.id
                WHERE ss.driver_id = :did
                  AND ss.firma_id = :fid
                  AND ss.kind IN ('pickup', 'dropoff')
                  AND ss.status != 'cancelled'
            """

            params = {"did": driver_id, "fid": current_firma_id}

            # Obsługa filtra miesiąca (YYYY-MM)
            if month_str:
                query += " AND to_char(ss.starts_at AT TIME ZONE 'Europe/Warsaw', 'YYYY-MM') = :month"
                params["month"] = month_str

            query += " ORDER BY ss.starts_at"

            # Bezpieczne wykonanie zapytania z mapowaniem kolumn
            result = conn.execute(text(query), params).mappings().all()
            routes = [dict(row) for row in result]

            # Konwersja pól numerycznych (Decimal -> float) na potrzeby formatu JSON
            for route in routes:
                if route.get('distance_km'):
                    route['distance_km'] = float(route['distance_km'])

            return jsonify(routes), 200

    except Exception as e:
        print(f"❌ Błąd w get_driver_schedule: {e}")
        import traceback
        traceback.print_exc()
        return jsonify({'error': str(e)}), 500


@app.route('/api/test-driver-gps/<int:driver_id>')
def test_driver_gps(driver_id):
    """TEST - Sprawdź czy GPS działa"""
    date = request.args.get('date', '2025-10-10')

    conn = psycopg2.connect(
        host='localhost', port='5432', database='suo',
        user='postgres', password='EDUQ'
    )
    cur = conn.cursor(cursor_factory=RealDictCursor)

    # Najprostsza możliwa kwerenda
    cur.execute("""
            SELECT 
                id, place_from, place_to,
                from_latitude, from_longitude,
                to_latitude, to_longitude,
                distance_km
            FROM schedule_slots
            WHERE driver_id = %s
            AND DATE(starts_at) = %s
            LIMIT 1
        """, (driver_id, date))

    result = cur.fetchone()
    cur.close()
    conn.close()

    return jsonify(dict(result) if result else {"error": "Brak danych"})


# OPCJONALNIE: Endpoint do przeliczania dystansu dla istniejących tras
@app.post("/api/schedule/recalculate-distances")
def recalculate_all_distances():
    """Przelicza dystansy dla wszystkich tras bez distance_km"""
    try:
        with engine.begin() as conn:
            # Znajdź wszystkie sloty bez dystansu
            rows = conn.execute(text("""
                    SELECT id, place_from, place_to
                    FROM schedule_slots
                    WHERE kind IN ('pickup', 'dropoff')
                    AND (distance_km IS NULL OR distance_km = 0)
                    AND place_from IS NOT NULL 
                    AND place_to IS NOT NULL
                """)).mappings().all()

            updated = 0
            for row in rows:
                distance = get_route_distance(row['place_from'], row['place_to'])
                if distance:
                    conn.execute(text("""
                            UPDATE schedule_slots 
                            SET distance_km = :dist 
                            WHERE id = :id
                        """), {"dist": distance, "id": row['id']})
                    updated += 1

            return jsonify({
                "message": f"Zaktualizowano {updated} tras",
                "total_checked": len(rows)
            }), 200

    except Exception as e:
        return jsonify({"error": str(e)}), 500


# ENDPOINT 1: Sprawdź czy API Google Maps działa
@app.get("/api/debug/test-google-maps")
def test_google_maps_api():
    """Testuje połączenie z Google Maps API"""
    try:
        print("\n=== TEST GOOGLE MAPS API ===")
        print(f"Klucz API: {GOOGLE_MAPS_API_KEY[:10]}..." if GOOGLE_MAPS_API_KEY else "BRAK KLUCZA!")

        # Test prosty
        origin = "Warszawa, Polska"
        destination = "Kraków, Polska"

        result = get_route_distance(origin, destination)

        return jsonify({
            "api_key_configured": bool(GOOGLE_MAPS_API_KEY),
            "api_key_preview": GOOGLE_MAPS_API_KEY[:10] + "..." if GOOGLE_MAPS_API_KEY else None,
            "test_route": f"{origin} -> {destination}",
            "calculated_distance_km": result,
            "status": "OK" if result else "FAILED"
        })
    except Exception as e:
        return jsonify({
            "error": str(e),
            "traceback": traceback.format_exc()
        }), 500


# ENDPOINT 2: Sprawdź co jest zapisane w bazie
@app.get("/api/debug/check-distances")
def check_existing_distances():
    """Sprawdź jakie dystanse są w bazie"""
    try:
        with engine.begin() as conn:
            result = conn.execute(text("""
                    SELECT 
                        id,
                        kind,
                        place_from,
                        place_to,
                        distance_km,
                        starts_at::date as date
                    FROM schedule_slots
                    WHERE kind IN ('pickup', 'dropoff')
                    ORDER BY starts_at DESC
                    LIMIT 20
                """))

            rows = [dict(row) for row in result.mappings().all()]

            stats = conn.execute(text("""
                    SELECT 
                        COUNT(*) as total,
                        COUNT(distance_km) as with_distance,
                        COUNT(*) - COUNT(distance_km) as without_distance,
                        AVG(distance_km) as avg_distance
                    FROM schedule_slots
                    WHERE kind IN ('pickup', 'dropoff')
                """)).mappings().first()

            return jsonify({
                "statistics": dict(stats),
                "recent_routes": rows
            })
    except Exception as e:
        return jsonify({"error": str(e)}), 500


# ENDPOINT 3: Test z logowaniem
@app.post("/api/debug/test-distance-calculation")
def test_distance_with_logging():
    """Test z pełnym logowaniem"""
    data = request.get_json()
    place_from = data.get('from')
    place_to = data.get('to')

    print("\n" + "=" * 60)
    print("TEST OBLICZANIA DYSTANSU")
    print("=" * 60)
    print(f"Od: {place_from}")
    print(f"Do: {place_to}")
    print(f"Klucz API ustawiony: {bool(GOOGLE_MAPS_API_KEY)}")

    if not GOOGLE_MAPS_API_KEY:
        print("BŁĄD: Brak klucza API!")
        return jsonify({"error": "Brak klucza GOOGLE_MAPS_API_KEY"}), 400

    try:
        # Wywołaj funkcję z logowaniem
        import requests

        origin_safe = requests.utils.quote(place_from)
        destination_safe = requests.utils.quote(place_to)
        url = f"https://maps.googleapis.com/maps/api/directions/json?origin={origin_safe}&destination={destination_safe}&key={GOOGLE_MAPS_API_KEY}"

        print(f"\nWysyłam zapytanie do Google Maps...")
        print(f"URL (bez klucza): {url.replace(GOOGLE_MAPS_API_KEY, 'HIDDEN')}")

        response = requests.get(url, timeout=10)
        print(f"Status code: {response.status_code}")

        data = response.json()
        print(f"Status odpowiedzi: {data.get('status')}")

        if data.get('status') == 'OK':
            distance_meters = data['routes'][0]['legs'][0]['distance']['value']
            distance_km = round(distance_meters / 1000, 2)
            print(f"✓ SUKCES! Dystans: {distance_km} km")

            return jsonify({
                "success": True,
                "distance_km": distance_km,
                "from": place_from,
                "to": place_to,
                "raw_response": data
            })
        else:
            print(f"✗ BŁĄD: {data.get('status')}")
            print(f"Szczegóły: {data.get('error_message', 'Brak')}")

            return jsonify({
                "success": False,
                "error": data.get('status'),
                "error_message": data.get('error_message'),
                "raw_response": data
            }), 400

    except Exception as e:
        print(f"✗ WYJĄTEK: {str(e)}")
        traceback.print_exc()
        return jsonify({
            "success": False,
            "error": str(e),
            "traceback": traceback.format_exc()
        }), 500
    finally:
        print("=" * 60 + "\n")


# ENDPOINT 4: Przelicz konkretną trasę ręcznie
@app.post("/api/debug/force-calculate-distance/<int:slot_id>")
def force_calculate_distance(slot_id):
    """Wymusza przeliczenie dystansu dla konkretnego slotu"""
    try:
        with engine.begin() as conn:
            # Pobierz slot
            result = conn.execute(text("""
                    SELECT id, place_from, place_to, distance_km
                    FROM schedule_slots
                    WHERE id = :sid
                """), {"sid": slot_id})

            slot = result.mappings().first()
            if not slot:
                return jsonify({"error": "Slot nie istnieje"}), 404

            print(f"\n=== WYMUSZAM PRZELICZENIE DLA SLOTU {slot_id} ===")
            print(f"Od: {slot['place_from']}")
            print(f"Do: {slot['place_to']}")
            print(f"Stary dystans: {slot['distance_km']}")

            # Oblicz nowy dystans
            new_distance = get_route_distance(slot['place_from'], slot['place_to'])
            print(f"Nowy dystans: {new_distance}")

            if new_distance:
                # Zapisz w bazie
                conn.execute(text("""
                        UPDATE schedule_slots
                        SET distance_km = :dist
                        WHERE id = :sid
                    """), {"dist": new_distance, "sid": slot_id})

                return jsonify({
                    "success": True,
                    "slot_id": slot_id,
                    "old_distance": slot['distance_km'],
                    "new_distance": new_distance,
                    "from": slot['place_from'],
                    "to": slot['place_to']
                })
            else:
                return jsonify({
                    "success": False,
                    "error": "Nie udało się obliczyć dystansu",
                    "slot_id": slot_id
                }), 400

    except Exception as e:
        return jsonify({
            "error": str(e),
            "traceback": traceback.format_exc()
        }), 500


@app.get("/api/clients/<int:client_id>/notes")
def get_client_notes(client_id):
    """Pobiera notatki dla danego klienta z opcjonalnym filtrem kategorii"""
    category = request.args.get('category')

    try:
        with engine.begin() as conn:
            # Sprawdź czy klient istnieje
            exists = conn.execute(
                text('SELECT 1 FROM clients WHERE id = :cid'),
                {"cid": client_id}
            ).scalar()

            if not exists:
                return jsonify({'error': 'Klient nie istnieje'}), 404

            # Pobierz notatki z filtrem lub bez
            if category and category != 'all':
                sql = text('''
                        SELECT id, client_id, content, category, 
                               created_by_name, created_at, updated_at
                        FROM client_notes
                        WHERE client_id = :cid AND category = :cat
                        ORDER BY created_at DESC
                    ''')
                result = conn.execute(sql, {"cid": client_id, "cat": category})
            else:
                sql = text('''
                        SELECT id, client_id, content, category, 
                               created_by_name, created_at, updated_at
                        FROM client_notes
                        WHERE client_id = :cid
                        ORDER BY created_at DESC
                    ''')
                result = conn.execute(sql, {"cid": client_id})

            notes = []
            for row in result.mappings().all():
                note = dict(row)
                # Konwertuj daty na ISO format
                if note['created_at']:
                    note['created_at'] = note['created_at'].isoformat()
                if note['updated_at']:
                    note['updated_at'] = note['updated_at'].isoformat()
                notes.append(note)

            return jsonify(notes), 200

    except Exception as e:
        print(f"Błąd w get_client_notes: {str(e)}")
        import traceback
        traceback.print_exc()
        return jsonify({'error': str(e)}), 500


@app.route("/api/clients/<int:client_id>/notes", methods=['POST'])
@login_required  # Wymagane, aby wiedzieć KTO dodaje notatkę
def add_client_note(client_id):
    """Dodaje nową notatkę dla klienta (z opcją daty wstecznej)"""
    data = request.get_json(silent=True) or {}

    content = (data.get('content') or '').strip()
    category = data.get('category', 'general')

    # Pobieramy autora z sesji (bardziej wiarygodne), fallback na frontend
    current_user_name = session.get('username') or session.get('full_name') or 'System'
    created_by_name = data.get('created_by_name') or current_user_name

    # Obsługa niestandardowej daty
    custom_date_str = data.get('created_at')
    created_at = datetime.now(TZ)  # Domyślnie teraz (z TZ)

    if custom_date_str:
        try:
            # Próbujemy sparsować datę przekazaną z frontendu
            # Usuwamy 'Z' i zamieniamy spację na T dla pewności
            clean_date = custom_date_str.replace('Z', '').replace(' ', 'T')
            dt = datetime.fromisoformat(clean_date)
            # Jeśli brak strefy, dodajemy TZ
            if dt.tzinfo is None:
                created_at = dt.replace(tzinfo=TZ)
            else:
                created_at = dt
        except ValueError:
            pass

    if not content:
        return jsonify({'error': 'Treść notatki jest wymagana'}), 400

    try:
        with session_scope() as db_session:
            # 1. Pobierz klienta (potrzebujemy nazwy do logów)
            client = db_session.get(Client, client_id)

            if not client:
                return jsonify({'error': 'Klient nie istnieje'}), 404

            # 2. Dodaj notatkę
            new_note = ClientNote(
                client_id=client_id,
                content=content,
                category=category,
                created_by_name=created_by_name,
                created_at=created_at,
                updated_at=created_at
            )

            db_session.add(new_note)
            db_session.flush()  # Aby uzyskać ID

            # 3. LOGOWANIE AKCJI
            # Skracamy treść do logów
            short_content = (content[:50] + '...') if len(content) > 50 else content
            log_msg = f"Dla: {client.full_name}. Kategoria: {category}. Treść: {short_content}"

            try:
                log_activity("DODANIE_NOTATKI", log_msg)
            except Exception as log_e:
                print(f"⚠️ Błąd zapisu logu: {log_e}")

            return jsonify({
                'id': new_note.id,
                'content': new_note.content,
                'created_at': new_note.created_at.isoformat(),
                'message': 'Notatka dodana pomyślnie'
            }), 201

    except Exception as e:
        print(f"Błąd w add_client_note: {str(e)}")
        import traceback
        traceback.print_exc()
        return jsonify({'error': str(e)}), 500


@app.put("/api/clients/<int:client_id>/notes/<int:note_id>")
@login_required  # Wymagane
def update_client_note(client_id, note_id):
    """Aktualizuje istniejącą notatkę"""
    data = request.get_json(silent=True) or {}

    content = (data.get('content') or '').strip()
    category = data.get('category')

    if not content:
        return jsonify({'error': 'Treść notatki jest wymagana'}), 400

    try:
        with engine.begin() as conn:
            # 1. Pobierz dane do weryfikacji i logowania
            # Sprawdzamy czy notatka istnieje ORAZ pobieramy nazwisko klienta w jednym ruchu
            check_sql = text('''
                SELECT c.full_name 
                FROM client_notes cn
                JOIN clients c ON c.id = cn.client_id
                WHERE cn.id = :nid AND cn.client_id = :cid
            ''')
            result = conn.execute(check_sql, {"nid": note_id, "cid": client_id}).mappings().first()

            if not result:
                return jsonify({'error': 'Notatka nie istnieje lub nie należy do tego klienta'}), 404

            client_name = result['full_name']

            # 2. Aktualizuj notatkę
            update_sql = text('''
                    UPDATE client_notes
                    SET content = :content,
                        category = :category,
                        updated_at = CURRENT_TIMESTAMP
                    WHERE id = :nid AND client_id = :cid
                    RETURNING id, client_id, content, category, created_by_name,
                              created_at, updated_at
                ''')

            result_update = conn.execute(update_sql, {
                "nid": note_id,
                "cid": client_id,
                "content": content,
                "category": category
            })

            note = dict(result_update.mappings().first())

            # Formatowanie daty dla JSON
            if note.get('created_at'):
                note['created_at'] = note['created_at'].isoformat()
            if note.get('updated_at'):
                note['updated_at'] = note['updated_at'].isoformat()

            # 3. LOGOWANIE
            try:
                log_activity("EDYCJA_NOTATKI", f"Zaktualizowano notatkę (ID: {note_id}) dla: {client_name}")
            except Exception:
                pass

            return jsonify(note), 200

    except Exception as e:
        print(f"Błąd w update_client_note: {str(e)}")
        import traceback
        traceback.print_exc()
        return jsonify({'error': str(e)}), 500


@app.delete("/api/clients/<int:client_id>/notes/<int:note_id>")
@login_required
def delete_client_note(client_id, note_id):
    """Usuwa notatkę"""
    try:
        with engine.begin() as conn:
            # Sprawdź czy notatka należy do tego klienta
            exists = conn.execute(text('''
                    SELECT 1 FROM client_notes 
                    WHERE id = :nid AND client_id = :cid
                '''), {"nid": note_id, "cid": client_id}).scalar()

            if not exists:
                return jsonify({'error': 'Notatka nie istnieje lub nie należy do tego klienta'}), 404

            # Usuń notatkę
            conn.execute(text('''
                    DELETE FROM client_notes
                    WHERE id = :nid AND client_id = :cid
                '''), {"nid": note_id, "cid": client_id})
            log_activity("USUNIECIE_NOTATEK", f"Usunięto notatkę ID: {note_id}, dla klienta: {client_id}")
            return jsonify({'message': 'Notatka usunięta pomyślnie'}), 200

    except Exception as e:
        print(f"Błąd w delete_client_note: {str(e)}")
        import traceback
        traceback.print_exc()
        return jsonify({'error': str(e)}), 500


@app.get("/api/clients/<int:client_id>/sessions")
def get_client_sessions(client_id):
    """Pobiera sesje terapii dla danego klienta z opcjonalnym filtrem miesiąca"""
    month = request.args.get('month')

    try:
        with engine.begin() as conn:
            # Sprawdź czy klient istnieje
            exists = conn.execute(
                text('SELECT 1 FROM clients WHERE id = :cid'),
                {"cid": client_id}
            ).scalar()

            if not exists:
                return jsonify({'error': 'Klient nie istnieje'}), 404

            # Zapytanie z filtrem miesiąca
            if month:
                sql = text('''
                        SELECT 
                            ss.id,
                            eg.label,
                            ss.starts_at,
                            ss.ends_at,
                            ss.place_to,
                            EXTRACT(EPOCH FROM (ss.ends_at - ss.starts_at))/60 as duration_minutes,
                            th.full_name as therapist_name,
                            cn.content as notes,
                            cn.id as note_id
                        FROM schedule_slots ss
                        LEFT JOIN event_groups eg ON eg.id = ss.group_id::uuid
                        LEFT JOIN therapists th ON th.id = ss.therapist_id
                        LEFT JOIN client_notes cn ON cn.client_id = ss.client_id 
                            AND DATE(cn.created_at) = DATE(ss.starts_at)
                            AND cn.category = 'session'
                        WHERE ss.client_id = :cid
                            AND ss.kind = 'therapy'
                            AND ss.starts_at IS NOT NULL
                            AND DATE_TRUNC('month', ss.starts_at) = DATE_TRUNC('month', TO_DATE(:month, 'YYYY-MM'))
                        ORDER BY ss.starts_at DESC
                    ''')
                result = conn.execute(sql, {"cid": client_id, "month": month + "-01"})
            else:
                sql = text('''
                        SELECT 
                            ss.id,
                            eg.label,
                            ss.starts_at,
                            ss.ends_at,
                            ss.place_to,
                            EXTRACT(EPOCH FROM (ss.ends_at - ss.starts_at))/60 as duration_minutes,
                            th.full_name as therapist_name,
                            cn.content as notes,
                            cn.id as note_id
                        FROM schedule_slots ss
                        LEFT JOIN event_groups eg ON eg.id = ss.group_id::uuid
                        LEFT JOIN therapists th ON th.id = ss.therapist_id
                        LEFT JOIN client_notes cn ON cn.client_id = ss.client_id 
                            AND DATE(cn.created_at) = DATE(ss.starts_at)
                            AND cn.category = 'session'
                        WHERE ss.client_id = :cid
                            AND ss.kind = 'therapy'
                            AND ss.starts_at IS NOT NULL
                        ORDER BY ss.starts_at DESC
                        LIMIT 100
                    ''')
                result = conn.execute(sql, {"cid": client_id})

            sessions = []
            for row in result.mappings().all():
                session = dict(row)
                if session['starts_at']:
                    session['starts_at'] = session['starts_at'].isoformat()
                if session['ends_at']:
                    session['ends_at'] = session['ends_at'].isoformat()
                if session['duration_minutes']:
                    session['duration_minutes'] = int(session['duration_minutes'])
                sessions.append(session)

            return jsonify(sessions), 200

    except Exception as e:
        print(f"Błąd w get_client_sessions: {str(e)}")
        import traceback
        traceback.print_exc()
        return jsonify({'error': str(e)}), 500


@app.get("/api/waiting-clients")
@login_required
def get_waiting_clients():
    """Pobiera listę klientów oczekujących z izolacją podmiotu."""
    status = request.args.get('status', 'oczekujący')
    page = request.args.get('page', 1, type=int)
    per_page = request.args.get('per_page', 50, type=int)
    current_firma_id = session.get('firma_id', 1)

    if page < 1: page = 1
    if per_page < 1 or per_page > 100: per_page = 50

    try:
        with engine.begin() as conn:
            sql = text("""
                SELECT id, first_name, last_name, birth_date, diagnosis, registration_date, notes, status,
                       CURRENT_DATE - registration_date as waiting_days, created_at, updated_at
                FROM waiting_clients
                WHERE (:status = 'all' OR status = :status) AND firma_id = :fid
                ORDER BY registration_date ASC LIMIT :limit OFFSET :offset
            """)
            result = conn.execute(sql, {
                "status": status, "limit": per_page, "offset": (page - 1) * per_page, "fid": current_firma_id
            })
            clients = []
            for row in result.mappings().all():
                client = dict(row)
                for date_field in ['birth_date', 'registration_date', 'created_at', 'updated_at']:
                    if client.get(date_field): client[date_field] = client[date_field].isoformat()
                clients.append(client)

            total = conn.execute(text("SELECT COUNT(*) FROM waiting_clients WHERE (:status = 'all' OR status = :status) AND firma_id = :fid"), {"status": status, "fid": current_firma_id}).scalar()
            return jsonify({'clients': clients, 'pagination': {'page': page, 'per_page': per_page, 'total': total, 'pages': (total + per_page - 1) // per_page}}), 200
    except Exception as e:
        return jsonify({'error': str(e)}), 500

@app.post("/api/waiting-clients")
@login_required
def add_waiting_client():
    """Dodaje nowego klienta do poczekalni w obrębie bieżącej firmy."""
    data = request.get_json(silent=True) or {}
    current_firma_id = session.get('firma_id', 1)
    
    required = ['first_name', 'last_name', 'birth_date']
    for field in required:
        if not data.get(field): return jsonify({'error': f'Pole {field} jest wymagane'}), 400

    first_name = data.get('first_name', '').strip()
    last_name = data.get('last_name', '').strip()

    try:
        with engine.begin() as conn:
            exists = conn.execute(text("SELECT 1 FROM waiting_clients WHERE first_name = :fname AND last_name = :lname AND birth_date = :bdate AND status = 'oczekujący' AND firma_id = :fid"),
                                  {"fname": first_name, "lname": last_name, "bdate": data['birth_date'], "fid": current_firma_id}).scalar()
            if exists: return jsonify({'error': 'Klient już istnieje na liście oczekujących'}), 409

            result = conn.execute(text("""
                INSERT INTO waiting_clients (first_name, last_name, birth_date, diagnosis, registration_date, notes, status, firma_id)
                VALUES (:fname, :lname, :bdate, :diag, :regdate, :notes, 'oczekujący', :fid) RETURNING id, first_name, last_name, registration_date, status
            """), {
                "fname": first_name, "lname": last_name, "bdate": data['birth_date'], "diag": data.get('diagnosis', '').strip(),
                "regdate": data.get('registration_date', date.today().isoformat()), "notes": data.get('notes', '').strip(), "fid": current_firma_id
            })
            new_client = dict(result.mappings().first())
            new_client['registration_date'] = new_client['registration_date'].isoformat()
            log_activity("DODANIE_DO_POCZEKALNI", f"Dodano: {first_name} {last_name} do firmy ID {current_firma_id}")
            return jsonify({'success': True, 'client': new_client, 'message': 'Klient dodany pomyślnie'}), 201
    except Exception as e:
        return jsonify({'error': str(e)}), 500


@app.put("/api/waiting-clients/<int:client_id>")
@login_required
def update_waiting_client(client_id):
    """Aktualizuje dane klienta oczekującego"""
    data = request.get_json(silent=True) or {}
    if not data:
        return jsonify({'error': 'Brak danych'}), 400

    try:
        with engine.begin() as conn:
            # Sprawdź istnienie
            old_data = conn.execute(
                text('SELECT first_name, last_name FROM waiting_clients WHERE id = :id'),
                {"id": client_id}
            ).mappings().first()

            if not old_data:
                return jsonify({'error': 'Klient nie znaleziony'}), 404

            # Budowanie UPDATE
            update_fields = []
            params = {"id": client_id}

            if 'first_name' in data:
                update_fields.append("first_name = :fname")
                params["fname"] = data['first_name'].strip()
            if 'last_name' in data:
                update_fields.append("last_name = :lname")
                params["lname"] = data['last_name'].strip()
            if 'birth_date' in data:
                update_fields.append("birth_date = :bdate")
                params["bdate"] = data['birth_date']
            if 'diagnosis' in data:
                update_fields.append("diagnosis = :diag")
                params["diag"] = data['diagnosis'].strip()
            if 'registration_date' in data:
                update_fields.append("registration_date = :regdate")
                params["regdate"] = data['registration_date']
            if 'notes' in data:
                update_fields.append("notes = :notes")
                params["notes"] = data['notes'].strip()
            if 'status' in data:
                update_fields.append("status = :status")
                params["status"] = data['status']

            if not update_fields:
                return jsonify({'error': 'Brak pól do aktualizacji'}), 400

            update_fields.append("updated_at = CURRENT_TIMESTAMP")

            sql = text(f'''
                    UPDATE waiting_clients
                    SET {', '.join(update_fields)}
                    WHERE id = :id
                    RETURNING id, first_name, last_name
                ''')

            result = conn.execute(sql, params)
            updated = result.mappings().first()

            # LOGOWANIE
            log_activity("EDYCJA_POCZEKALNI",
                         f"Zaktualizowano: {updated['first_name']} {updated['last_name']} (ID: {client_id})")

            return jsonify({'success': True, 'message': 'Zaktualizowano'}), 200

    except Exception as e:
        print(f"Błąd edycji poczekalni: {e}")
        return jsonify({'error': str(e)}), 500


@app.delete("/api/waiting-clients/<int:client_id>")
@login_required
def delete_waiting_client(client_id):
    """Soft delete - zmienia status na 'anulowany'"""
    try:
        with engine.begin() as conn:
            # Pobierz dane przed zmianą (do logów)
            row = conn.execute(
                text("SELECT first_name, last_name FROM waiting_clients WHERE id=:id"),
                {"id": client_id}
            ).mappings().first()

            if not row:
                return jsonify({'error': 'Nie znaleziono'}), 404

            # Wykonaj UPDATE
            result = conn.execute(
                text("UPDATE waiting_clients SET status = 'anulowany', updated_at = NOW() WHERE id = :id"),
                {"id": client_id}
            )

            # LOGOWANIE
            log_activity("ANULOWANIE_POCZEKALNI",
                         f"Anulowano zgłoszenie: {row['first_name']} {row['last_name']} (ID: {client_id})")

            return jsonify({'success': True, 'message': 'Anulowano zgłoszenie'}), 200

    except Exception as e:
        return jsonify({'error': str(e)}), 500


@app.post("/api/waiting-clients/<int:client_id>/accept")
@login_required
def accept_waiting_client(client_id):
    """Przenosi klienta z poczekalni do głównych zasobów aktywnego podmiotu."""
    current_firma_id = session.get('firma_id', 1)
    try:
        with engine.begin() as conn:
            waiting = conn.execute(text("SELECT * FROM waiting_clients WHERE id = :id AND firma_id = :fid"), {"id": client_id, "fid": current_firma_id}).mappings().first()
            if not waiting: return jsonify({'error': 'Klient nie znaleziony lub brak uprawnień'}), 404
            if waiting['status'] == 'przyjęty': return jsonify({'error': 'Ten klient został już przyjęty!'}), 409

            full_name = f"{waiting['first_name']} {waiting['last_name']}"
            exists_main = conn.execute(text("SELECT 1 FROM clients WHERE full_name = :fn AND firma_id = :fid"), {"fn": full_name, "fid": current_firma_id}).scalar()
            
            if not exists_main:
                conn.execute(text("""
                    INSERT INTO clients (full_name, active, birth_date, diagnosis, notes, firma_id)
                    VALUES (:name, true, :bdate, :diag, :notes, :fid)
                """), {"name": full_name, "bdate": waiting.get('birth_date'), "diag": waiting.get('diagnosis'), "notes": waiting.get('notes'), "fid": current_firma_id})
                msg = "Klient został przeniesiony do bazy głównej podmiotu."
            else:
                msg = "Klient o takim nazwisku już istnieje w podmiocie. Zmieniono status wniosku."

            conn.execute(text("UPDATE waiting_clients SET status = 'przyjęty', updated_at = NOW() WHERE id = :id AND firma_id = :fid"), {"id": client_id, "fid": current_firma_id})
            log_activity("PRZYJECIE_Z_POCZEKALNI", f"Zaakceptowano: {full_name} w firmie {current_firma_id}")
            return jsonify({'success': True, 'message': msg}), 200
    except Exception as e:
        return jsonify({'error': str(e)}), 500


@app.get("/api/waiting-clients/stats")
@login_required
def get_waiting_stats():
    """Zwraca odizolowane statystyki poczekalni."""
    current_firma_id = session.get('firma_id', 1)
    try:
        with engine.begin() as conn:
            stats = conn.execute(text("""
                SELECT COUNT(*) FILTER (WHERE status = 'oczekujący') as oczekujacy,
                       COUNT(*) FILTER (WHERE status = 'przyjęty') as przyjeci,
                       COUNT(*) FILTER (WHERE status = 'anulowany') as anulowani,
                       ROUND(AVG(CURRENT_DATE - registration_date) FILTER (WHERE status = 'oczekujący')) as sredni_czas_dni
                FROM waiting_clients WHERE firma_id = :fid
            """), {"fid": current_firma_id}).mappings().first()
            return jsonify(dict(stats)), 200
    except Exception as e:
        return jsonify({'error': str(e)}), 500

    # === DZIENNIK ENDPOINTS ===


# @app.get("/api/journal")
# def get_journal_entries():
#        """Pobiera wszystkie wpisy z dziennika z pełnymi nazwami"""

# Opcjonalny filtr na klienta
#        client_id = request.args.get('client_id', type=int)

#        with session_scope() as db_session:
#            query = db_session.query(JournalEntry).options(
#                joinedload(JournalEntry.client),
#                joinedload(JournalEntry.therapist)
#            )

#           if client_id:
#               query = query.filter(JournalEntry.client_id == client_id)

#          entries = query.order_by(JournalEntry.data.desc(), JournalEntry.id.desc()).all()

#          results = []
#          for e in entries:
# Upewnij się, że używasz bezpiecznego dostępu do relacji
#              client_name = e.client.full_name if e.client else 'Nieznany Klient'
#              therapist_name = e.therapist.full_name if e.therapist else 'Nieznany Terapeuta'

#              results.append({
#                  "id": e.id,
#                  "data": e.data.isoformat(),
#                  "client_id": e.client_id,
#                  "klient": client_name,
#                  "therapist_id": e.therapist_id,
#                  "terapeuta": therapist_name,
#                  "temat": e.temat,
#                  "cele": e.cele,
#                  "created_at": e.created_at.isoformat() if e.created_at else None
#              })

#         return jsonify(results), 200


@app.route('/api/journal', methods=['GET'])
@login_required # <--- Zawsze wymagaj logowania w systemach wielopodmiotowych!
def get_journal_entries():
    """Pobiera wpisy dziennika z uwzględnieniem podmiotu (Multi-tenant)."""
    try:
        client_id_param = request.args.get('client_id')
        month_str = request.args.get('month')
        
        # Pobieranie firma_id z sesji (domyślnie 1 jako fallback)
        current_firma_id = session.get('firma_id', 1)

        with session_scope() as db_session:
            query = db_session.query(JournalEntry).options(
                joinedload(JournalEntry.client),
                joinedload(JournalEntry.therapist)
            ).filter(JournalEntry.firma_id == current_firma_id) # <--- BLOKADA MULTI-TENANT

            # FILTROWANIE PO KLIENTA ID
            if client_id_param:
                try:
                    client_id = int(client_id_param)
                    query = query.filter(JournalEntry.client_id == client_id)
                except (ValueError, TypeError):
                    pass # Zignoruj błędny format ID

            # FILTROWANIE PO MIESIĄCU
            if month_str:
                try:
                    year, month = map(int, month_str.split('-'))
                    query = query.filter(extract('year', JournalEntry.data) == year)
                    query = query.filter(extract('month', JournalEntry.data) == month)
                except (ValueError, TypeError):
                    pass

            # Wykonaj zapytanie, sortując od najnowszych
            entries = query.order_by(JournalEntry.data.desc(), JournalEntry.id.desc()).all()

            # Mapowanie obiektów na słownik JSON z tzw. "Safety Checks" (Zabezpieczenia przed NULL)
            results = []
            for e in entries:
                # Ochrona przed usuniętymi klientami (jeśli baza nie ma CASCADE)
                client_name = 'Nieznany Klient'
                if e.client and hasattr(e.client, 'full_name'):
                    client_name = e.client.full_name
                    
                # Ochrona przed usuniętymi terapeutami
                therapist_name = 'Nieznany Terapeuta'
                if e.therapist and hasattr(e.therapist, 'full_name'):
                    therapist_name = e.therapist.full_name
                    
                # Formatowanie daty i radzenie sobie z pustymi dniami (choć data jest NOT NULL)
                try:
                    data_iso = e.data.isoformat() if e.data else ""
                except Exception:
                    data_iso = ""

                results.append({
                    "id": e.id,
                    "data": data_iso,
                    "client_id": e.client_id,
                    "klient": client_name,
                    "therapist_id": e.therapist_id,
                    "terapeuta": therapist_name,
                    "temat": e.temat if e.temat else "",
                    "cele": e.cele if e.cele else "",
                })

            return jsonify(results), 200

    except Exception as e:
        print(f"⚠️ PANCERNY TRY-EXCEPT: Błąd krytyczny w get_journal_entries: {e}")
        import traceback
        traceback.print_exc()
        
        # Nawet jeśli wszystko wybuchnie (np. zepsuty join na usuniętym pacjencie),
        # wyślemy do axiosa PUSTĄ LISTĘ z kodem sukcesu, byle tylko strona się odpaliła.
        return jsonify([]), 200


@app.post('/api/journal')
@login_required
def save_general_journal_entry():
    """Zapisuje wpis do dziennika z obsługą Multi-Tenant"""
    payload = request.get_json()

    if not payload:
        return jsonify({'error': 'Brak danych'}), 400

    client_id = payload.get('client_id')
    if not client_id:
        return jsonify({'error': 'Brak ID klienta'}), 400

    try:
        saved_id = None

        with session_scope() as db_session:
            # 1. Tworzenie obiektu Z PRZYPISANIEM DO FUNDACJI
            new_entry = JournalEntry(
                firma_id=session.get('firma_id', 1), # <--- KLUCZOWA POPRAWKA
                client_id=int(client_id),
                therapist_id=payload.get('therapist_id') or session.get('user_id'),
                data=payload.get('data'),
                temat=payload.get('temat', '').strip(),
                cele=payload.get('cele', '').strip(),
                created_at=datetime.now(TZ),
                updated_at=datetime.now(TZ)
            )

            db_session.add(new_entry)
            db_session.flush()
            saved_id = new_entry.id

            # Logowanie
            temat_txt = payload.get('temat', '')
            short_topic = (temat_txt[:40] + '...') if len(temat_txt) > 40 else temat_txt
            log_activity("DODANIE_SESJI", f"Klient ID: {client_id}. Temat: {short_topic}")

        return jsonify({"success": True, "id": saved_id}), 201

    except Exception as e:
        print(f"Błąd zapisu sesji: {e}")
        import traceback
        traceback.print_exc()
        return jsonify({'error': 'Błąd serwera'}), 500


@app.get("/api/journal/<int:entry_id>")
def get_journal_entry(entry_id):
    """Pobiera pojedynczy wpis z dziennika"""
    with session_scope() as db_session:
        entry = db_session.query(JournalEntry).options(
            joinedload(JournalEntry.client),
            joinedload(JournalEntry.therapist)
        ).filter(JournalEntry.id == entry_id).first()

        if not entry:
            return jsonify({"error": "Wpis nie znaleziony"}), 404

        return jsonify({
            "id": entry.id,
            "data": entry.data.isoformat(),
            "client_id": entry.client_id,
            "klient": entry.client.full_name if entry.client else 'Nieznany Klient',
            "therapist_id": entry.therapist_id,
            "terapeuta": entry.therapist.full_name if entry.therapist else 'Nieznany Terapeuta',
            "temat": entry.temat,
            "cele": entry.cele,
            "updated_at": entry.updated_at.isoformat() if entry.updated_at else None
        }), 200


# --- ZABEZPIECZONA FUNKCJA UPDATE ---
# --- ZABEZPIECZONA FUNKCJA UPDATE ---
@app.route("/api/journal/<int:entry_id>", methods=['PUT', 'PATCH'])  # Połączyłem metody w jeden dekorator
@login_required
def update_journal_entry(entry_id):
    """Aktualizuje wpis w dzienniku (Naprawiony błąd DetachedInstanceError)"""
    data = request.get_json(silent=True) or {}

    def safe_int(value, field_name):
        if value is None: return None
        try:
            if str(value).lower() in ('', 'undefined'): return None
            return int(value)
        except ValueError:
            raise ValueError(f"Nieprawidłowy format {field_name}: '{value}'.")

    try:
        # Zmienne do przechowywania danych po commicie
        saved_info = {}

        with session_scope() as db_session:
            entry = db_session.get(JournalEntry, entry_id)  # Nowsza składnia zamiast query().get()
            if not entry:
                return jsonify({"error": "Wpis nie znaleziony"}), 404

            # --- AKTUALIZACJA PÓL ---
            if "data" in data:
                try:
                    # Obsługa formatu daty
                    entry.data = data["data"]
                except Exception:
                    # Fallback jeśli to string YYYY-MM-DD
                    pass

            if "client_id" in data:
                cid = safe_int(data["client_id"], "ID klienta")
                if cid is not None: entry.client_id = cid

            if "therapist_id" in data:
                tid = safe_int(data["therapist_id"], "ID terapeuty")
                if tid is not None: entry.therapist_id = tid

            if "temat" in data: entry.temat = data["temat"]
            if "cele" in data: entry.cele = data["cele"]

            # Aktualizacja updated_at
            entry.updated_at = datetime.now(TZ)

            # --- ZAPIS DANYCH DO ZMIENNYCH (PRZED COMMITEM) ---
            # To jest kluczowe! Kopiujemy dane do słownika, bo 'entry' zaraz wygaśnie.
            saved_info = {
                "id": entry.id,
                "temat": entry.temat,
                "cele": entry.cele
            }

            db_session.flush()  # Upewnij się, że zmiany są "zaklepane" w tej transakcji

            # --- LOGOWANIE (W TEJ SAMEJ TRANSAKCJI) ---
            try:
                log_activity(
                    "EDYCJA_DZIENNIKA",
                    f"ID: {saved_info['id']}. Temat: {saved_info['temat']}, Cele: {saved_info['cele']}"
                )
            except Exception as log_e:
                print(f"⚠️ Błąd zapisu logu edycji dziennika: {log_e}")

        # Poza blokiem with zwracamy odpowiedź
        return jsonify({"id": saved_info['id'], "message": "Wpis zaktualizowany."}), 200

    except ValueError as e:
        return jsonify({"error": str(e)}), 400
    except Exception as e:
        print(f"Błąd edycji: {e}")
        import traceback
        traceback.print_exc()
        return jsonify({"error": "Błąd serwera podczas aktualizacji"}), 500


@app.delete("/api/journal/<int:entry_id>")
@login_required
def delete_journal_entry(entry_id):
    """Usuwa wpis z dziennika"""
    try:
        with session_scope() as db_session:
            entry = db_session.get(JournalEntry, entry_id)

            if not entry:
                return jsonify({"error": "Wpis nie znaleziony"}), 404

            # --- ZABEZPIECZENIE DANYCH DO LOGA (PRZED USUNIĘCIEM) ---
            del_id = entry.id
            del_temat = entry.temat
            # --------------------------------------------------------

            db_session.delete(entry)

            # --- LOGOWANIE (W TEJ SAMEJ TRANSAKCJI) ---
            try:
                log_activity(
                    "USUNIECIE_DZIENNIKA",
                    f"Usunięto wpis ID: {del_id}, Temat: {del_temat}"
                )
            except Exception as log_e:
                print(f"⚠️ Błąd zapisu logu usunięcia dziennika: {log_e}")

        return jsonify({"message": "Wpis usunięty pomyślnie"}), 200

    except Exception as e:
        print(f"Błąd usuwania wpisu dziennika: {e}")
        return jsonify({"error": str(e)}), 500


@app.get("/api/clients/<int:client_id>/all-sessions")
def get_client_all_sessions(client_id: int):
    """
    Zwraca ujednoliconą historię spotkań klienta.
    Opcjonalnie filtruje po roku (YYYY).
    """
    year = request.args.get('year')  # Zmiana z 'month' na 'year'
    params = {"cid": client_id}

    # Ustaw filtr roku jeśli podany
    if year:
        try:
            datetime.strptime(year, '%Y')  # Walidacja formatu YYYY
            params['year_key'] = year
        except ValueError:
            print(f"OSTRZEŻENIE: Nieprawidłowy format roku: {year}")
            year = None

    try:
        with engine.begin() as conn:
            # Zapytanie z filtrem roku
            sql_query = text('''
                -- 1. Sesje Indywidualne
                SELECT 
                    ss.id as source_id,
                    'individual' as source_type,
                    ss.starts_at,
                    ss.ends_at,
                    ss.status,
                    th.full_name as therapist_name,
                    eg.label as topic_or_temat,
                    ss.place_to as place,
                    EXTRACT(EPOCH FROM (ss.ends_at - ss.starts_at))/60 as duration_minutes,
                    cn.content as notes,
                    cn.id as note_id,
                    ss.id as session_id
                FROM schedule_slots ss
                LEFT JOIN therapists th ON th.id = ss.therapist_id
                LEFT JOIN event_groups eg ON eg.id = ss.group_id
                LEFT JOIN client_notes cn ON cn.client_id = ss.client_id 
                    AND DATE(cn.created_at) = DATE(ss.starts_at)
                    AND cn.category = 'session'
                WHERE ss.client_id = :cid
                    AND ss.kind = 'therapy'
                    AND (:year_key IS NULL OR TO_CHAR(ss.starts_at AT TIME ZONE 'Europe/Warsaw', 'YYYY') = :year_key)

                UNION ALL

                -- 2. Wpisy z Dziennika
                SELECT 
                    d.id as source_id,
                    'journal' as source_type,
                    d.data::timestamp AS starts_at, 
                    (d.data + interval '60 minutes')::timestamp AS ends_at,
                    'done' as status,
                    (SELECT full_name FROM therapists WHERE id = d.therapist_id) as therapist_name,
                    d.temat as topic_or_temat,
                    'Dziennik' as place,
                    60 as duration_minutes,
                    d.cele as notes,
                    NULL as note_id,
                    NULL as session_id
                FROM dziennik d
                WHERE d.client_id = :cid
                    AND (:year_key IS NULL OR TO_CHAR(d.data, 'YYYY') = :year_key)

                ORDER BY starts_at DESC
            ''')

            # Jeśli nie ma roku, ustaw year_key na None
            if not year:
                params['year_key'] = None

            print(f"DEBUG: Wykonywanie zapytania z parametrami: {params}")
            rows = conn.execute(sql_query, params).mappings().all()
            print(f"DEBUG: Znaleziono {len(rows)} rekordów")

            # Przetwarzanie wyników
            history = []
            for row in rows:
                row_dict = dict(row)

                # Konwersja dat
                for date_field in ['starts_at', 'ends_at']:
                    if row_dict[date_field]:
                        dt = row_dict[date_field]
                        if dt.tzinfo is None:
                            row_dict[date_field] = dt.replace(tzinfo=ZoneInfo('Europe/Warsaw')).isoformat()
                        else:
                            row_dict[date_field] = dt.isoformat()

                # Konwersja czasu trwania
                if row_dict['duration_minutes'] is not None:
                    row_dict['duration_minutes'] = int(row_dict['duration_minutes'])

                history.append(row_dict)

            return jsonify(history), 200

    except Exception as e:
        print(f"❌ BŁĄD w get_client_all_sessions: {str(e)}")
        traceback.print_exc()
        return jsonify({"error": str(e)}), 500





@app.route('/badanie/diva5/<client_uuid>', methods=['GET'])
def public_diva5_test(client_uuid):
    """Wyświetla formularz pacjentowi na podstawie bezpiecznego tokenu."""
    try:
        with session_scope() as db_session:
            # Szukamy pacjenta po jego unikalnym tokenie
            client = db_session.query(Client).filter_by(public_token=client_uuid).first()

            if not client:
                return "Nieprawidłowy link lub badanie zostało już zakończone.", 404

            # Przekazujemy token do szablonu HTML
            return render_template('diva5.html', client_token=client_uuid)

    except Exception as e:
        print(f"Błąd otwierania publicznego DIVA-5: {e}")
        return "Błąd serwera.", 500


@app.route('/api/public/diva5/<client_uuid>', methods=['POST'])
def save_public_diva5_results(client_uuid):
    """Zapisuje wynik badania zrobionego przez pacjenta do jego profilu."""
    data = request.get_json()
    content = data.get('content')

    if not content:
        return jsonify({'error': 'Brak treści wyniku.'}), 400

    try:
        with session_scope() as db_session:
            client = db_session.query(Client).filter_by(public_token=client_uuid).first()

            if not client:
                return jsonify({'error': 'Nieprawidłowy lub wygasły link.'}), 404

            # 1. Zapisujemy raport w profilu klienta
            new_report = ClientReport(
                client_id=client.id,
                content=content,
                period='Wynik badania DIVA-5 (Wypełniono zdalnie)'
            )
            db_session.add(new_report)

            # 2. OPCJONALNIE: Zmiana tokenu, aby link był JEDNORAZOWY
            # Jeśli pacjent odświeży stronę, już nie zobaczy formularza
            import uuid
            client.public_token = str(uuid.uuid4())

            log_activity("WYPEŁNIENIE_DIVA5", f"Pacjent {client.full_name} przesłał zdalnie formularz DIVA-5.")

        return jsonify({'message': 'Dziękujemy! Twoje badanie zostało przesłane do specjalisty.'}), 201

    except Exception as e:
        print(f"Błąd zapisu publicznego DIVA-5: {e}")
        return jsonify({'error': 'Wystąpił błąd podczas zapisywania.'}), 500


# ==========================================
# === ZARZĄDZANIE WYNIKAMI DIVA-5 (ADMIN) ===
# ==========================================

@app.route('/manager/diva5-raporty')
@login_required
def diva5_reports_page():
    """Wyświetla stronę z listą nadesłanych kwestionariuszy DIVA-5."""
    return render_template('diva5_reports.html')


@app.route('/api/reports/diva5', methods=['GET'])
@login_required
def get_diva5_reports():
    """Pobiera raporty DIVA-5 wyłącznie dla pacjentów należących do bieżącej firmy."""
    try:
        # POBIERAMY ID FIRMY Z SESJI
        current_firma_id = session.get('firma_id', 1)

        with session_scope() as db_session:
            # POPRAWKA: Dodano krytyczny warunek filtrujący po firmie pacjenta
            # (Client.firma_id == current_firma_id)
            records = db_session.query(ClientReport, Client).join(
                Client, ClientReport.client_id == Client.id
            ).filter(
                Client.firma_id == current_firma_id,
                ClientReport.period.ilike('%DIVA-5%')
            ).order_by(ClientReport.created_at.desc()).all()

            result = []
            for report, client in records:
                result.append({
                    'id': report.id,
                    'client_id': client.id,
                    'client_name': client.full_name,
                    'dob': client.birth_date.isoformat() if client.birth_date else 'Brak danych',
                    'content': report.content,
                    'period': report.period,
                    'created_at': report.created_at.strftime('%Y-%m-%d %H:%M') if report.created_at else '-'
                })
            return jsonify(result), 200

    except Exception as e:
        print(f"❌ Błąd pobierania raportów DIVA-5: {e}")
        import traceback
        traceback.print_exc()
        return jsonify({'error': str(e)}), 500

    except Exception as e:
        print(f"Błąd pobierania raportów DIVA-5: {e}")
        import traceback
        traceback.print_exc()  # Dodaję to, by w konsoli Render było widać dokładną linię błędu na przyszłość
        return jsonify({'error': str(e)}), 500

# Funkcja do znalezienia wszystkich duplikatów endpointów
def debug_endpoints():
    print("\n=== DEBUG: WSZYSTKIE ENDPOINTY ===")
    endpoints = {}

    for rule in app.url_map.iter_rules():
        key = f"{rule.rule}::{','.join(rule.methods)}"
        if key in endpoints:
            print(f"🚨 DUPLIKAT: {key}")
            print(f"   Istniejący: {endpoints[key]}")
            print(f"   Nowy: {rule.endpoint}")
        else:
            endpoints[key] = rule.endpoint

    print(f"✓ Łącznie endpointów: {len(endpoints)}")
    return endpoints


@app.route('/api/debug/users')
def debug_users():
    """Debug - pokaż wszystkich użytkowników"""
    try:
        with session_scope() as db_session:
            users = db_session.query(User).all()
            result = []
            for user in users:
                result.append({
                    'id': user.id,
                    'username': user.username,
                    'is_admin': user.is_admin,
                    'password_hash_length': len(user.password_hash) if user.password_hash else 0,
                    'password_hash_preview': user.password_hash[:30] + '...' if user.password_hash else 'EMPTY'
                })
            return jsonify(result)
    except Exception as e:
        return jsonify({'error': str(e)})


# ==========================================
# === ENDPOINTY DLA UCHWAŁ ZARZĄDU (CRUD) ===
# ==========================================

@app.route('/api/resolutions', methods=['GET'])
@login_required
def get_resolutions():
    year = request.args.get('year')
    current_firma_id = session.get('firma_id', 1)
    try:
        with session_scope() as db_session:
            query = db_session.query(BoardResolution).filter(BoardResolution.firma_id == current_firma_id)
            if year:
                query = query.filter(extract('year', BoardResolution.resolution_date) == int(year))
            resolutions = query.order_by(desc(BoardResolution.resolution_date)).all()
            return jsonify([r.as_dict() for r in resolutions]), 200
    except Exception as e:
        return jsonify({'error': str(e)}), 500


@app.route('/api/resolutions', methods=['POST'])
@login_required
def create_resolution():
    """Tworzy nową uchwałę z opcjonalnym plikiem"""
    title = request.form.get('title')
    date_str = request.form.get('resolution_date')
    description = request.form.get('description')
    file = request.files.get('file')

    if not title or not date_str:
        return jsonify({'error': 'Tytuł i data uchwały są wymagane'}), 400

    try:
        resolution_date = datetime.fromisoformat(date_str).date()
    except ValueError:
        return jsonify({'error': 'Nieprawidłowy format daty (wymagany YYYY-MM-DD)'}), 400

    file_path = None
    file_name = None

    try:
        # Obsługa pliku
        if file and file.filename:
            if not allowed_file(file.filename):
                return jsonify({'error': 'Niedozwolony format pliku'}), 400

            original_filename = secure_filename(file.filename)
            unique_name = f"{uuid.uuid4()}_{original_filename}"

            # Upewnij się, że folder istnieje
            upload_folder = app.config['RESOLUTIONS_UPLOAD_FOLDER']
            os.makedirs(upload_folder, exist_ok=True)

            file_path = os.path.join(upload_folder, unique_name)
            file_name = original_filename
            file.save(file_path)

        with session_scope() as db_session:
            new_res = BoardResolution(
                title=title,
                resolution_date=resolution_date,
                description=description,
                file_path=file_path,
                file_name=file_name
            )
            db_session.add(new_res)
            db_session.flush()  # Aby uzyskać ID

            # LOGOWANIE
            try:
                log_activity("DODANIE_UCHWALY", f"Utworzono: '{title}' (ID: {new_res.id})")
            except Exception:
                pass

            return jsonify(new_res.as_dict()), 201

    except Exception as e:
        # Sprzątanie pliku w razie błędu
        if file_path and os.path.exists(file_path):
            try:
                os.remove(file_path)
            except:
                pass
        print(f"Błąd tworzenia uchwały: {e}")
        return jsonify({'error': str(e)}), 500


@app.route('/api/resolutions/<int:res_id>', methods=['PUT'])
@login_required
def update_resolution(res_id):
    """Aktualizuje uchwałę (dane i/lub plik)"""
    title = request.form.get('title')
    date_str = request.form.get('resolution_date')
    description = request.form.get('description')
    file = request.files.get('file')

    try:
        with session_scope() as db_session:
            resolution = db_session.get(BoardResolution, res_id)
            if not resolution:
                return jsonify({'error': 'Uchwała nie znaleziona'}), 404

            # Aktualizacja pól tekstowych
            if title: resolution.title = title
            if description: resolution.description = description
            if date_str:
                try:
                    resolution.resolution_date = datetime.fromisoformat(date_str).date()
                except ValueError:
                    return jsonify({'error': 'Błędna data'}), 400

            # Aktualizacja pliku
            if file and file.filename:
                # 1. Usuń stary plik
                if resolution.file_path and os.path.exists(resolution.file_path):
                    try:
                        os.remove(resolution.file_path)
                    except OSError:
                        pass

                # 2. Zapisz nowy plik
                original_filename = secure_filename(file.filename)
                unique_name = f"{uuid.uuid4()}_{original_filename}"

                upload_folder = app.config['RESOLUTIONS_UPLOAD_FOLDER']
                os.makedirs(upload_folder, exist_ok=True)
                new_path = os.path.join(upload_folder, unique_name)

                file.save(new_path)

                resolution.file_path = new_path
                resolution.file_name = original_filename

            # LOGOWANIE
            try:
                log_activity("EDYCJA_UCHWALY", f"Zaktualizowano uchwałę ID: {res_id}, Tytuł: {resolution.title}")
            except Exception:
                pass

            return jsonify(resolution.as_dict()), 200

    except Exception as e:
        print(f"Błąd aktualizacji uchwały: {e}")
        return jsonify({'error': str(e)}), 500


@app.delete("/api/clients/<int:client_id>/unavailability")
@login_required  # Wymagane dla bezpieczeństwa
def delete_client_schedule(client_id):
    """Usuwa WSZYSTKIE wpisy niedostępności dla danego klienta."""
    try:
        sql = text("DELETE FROM client_unavailability WHERE client_id = :cid")
        with engine.begin() as conn:
            conn.execute(sql, {"cid": client_id})

        # LOGOWANIE
        log_activity("USUNIECIE_DOSTEPNOSCI", f"Wyczyszczono grafik niedostępności dla klienta ID: {client_id}")

        return "", 204
    except Exception as e:
        print(f"Błąd usuwania dostępności: {e}")
        return jsonify({'error': str(e)}), 500


@app.route('/api/resolutions/<int:res_id>', methods=['DELETE'])
@login_required
def delete_resolution(res_id):
    current_firma_id = session.get('firma_id', 1)
    try:
        with session_scope() as db_session:
            resolution = db_session.query(BoardResolution).filter_by(id=res_id, firma_id=current_firma_id).first()
            if not resolution: return jsonify({'error': 'Uchwała nie znaleziona'}), 404
            
            file_path = resolution.file_path
            deleted_title = resolution.title
            db_session.delete(resolution)
            
            if file_path and os.path.exists(file_path):
                try: os.remove(file_path)
                except OSError: pass
                
            log_activity("USUNIECIE_UCHWALY", f"Usunięto: '{deleted_title}' w firmie {current_firma_id}")
            return jsonify({'message': 'Uchwała usunięta'}), 200
    except Exception as e:
        return jsonify({'error': str(e)}), 500


# In app.py

def get_driver_availability(days_ahead=14):
    """
    Pobiera listę aktywnych kierowców i ich ZAJĘTE terminy.
    Zwraca: (lista_kierowcow, mapa_zajetosci)
    """
    now = datetime.now()
    end_date = now + timedelta(days=days_ahead)
    start_str = now.strftime('%Y-%m-%d 00:00:00')
    end_str = end_date.strftime('%Y-%m-%d 23:59:59')

    drivers_info = []
    busy_slots = {}

    try:
        with engine.connect() as conn:
            # 1. Pobierz aktywnych kierowców
            drivers_res = conn.execute(text("SELECT id, full_name FROM drivers WHERE active = true"))
            for row in drivers_res:
                drivers_info.append({"id": row.id, "name": row.full_name})
                busy_slots[row.id] = []

            # 2. Pobierz ich zajęte sloty (pickup/dropoff)
            if drivers_info:
                ids = tuple(d['id'] for d in drivers_info)
                ids_sql = str(ids) if len(ids) > 1 else f"({ids[0]})"

                query = text(f"""
                    SELECT driver_id, starts_at, ends_at 
                    FROM schedule_slots 
                    WHERE driver_id IN {ids_sql}
                      AND starts_at >= :start
                      AND ends_at <= :end
                      AND status != 'cancelled'
                    ORDER BY starts_at ASC
                """)

                slots_res = conn.execute(query, {"start": start_str, "end": end_str})

                for row in slots_res:
                    # Format: "2025-12-15 10:00-11:00"
                    slot_str = f"{row.starts_at.strftime('%Y-%m-%d %H:%M')}-{row.ends_at.strftime('%H:%M')}"
                    if row.driver_id in busy_slots:
                        busy_slots[row.driver_id].append(slot_str)

    except Exception as e:
        print(f"⚠️ Błąd pobierania kierowców: {e}")
        return [], {}

    return drivers_info, busy_slots


def get_availability_data(therapist_ids, days_ahead=14):
    """
    Pobiera ZAJĘTE terminy (BUSY slots) dla listy terapeutów.
    """
    if not therapist_ids:
        return {}

    clean_ids = list(set([int(x) for x in therapist_ids if x]))
    if not clean_ids:
        return {}

    now = datetime.now()
    end_date = now + timedelta(days=days_ahead)
    start_str = now.strftime('%Y-%m-%d 00:00:00')
    end_str = end_date.strftime('%Y-%m-%d 23:59:59')

    # Bezpieczne formatowanie SQL IN (...)
    tids_sql = f"({','.join(map(str, clean_ids))})"

    busy_slots = {tid: [] for tid in clean_ids}

    try:
        with engine.connect() as conn:
            query = text(f"""
                SELECT therapist_id, starts_at, ends_at 
                FROM schedule_slots 
                WHERE therapist_id IN {tids_sql}
                  AND starts_at >= :start
                  AND ends_at <= :end
                  AND status != 'cancelled'
                ORDER BY starts_at ASC
            """)

            result = conn.execute(query, {"start": start_str, "end": end_str})

            for row in result:
                tid = row.therapist_id
                # Format czytelny dla AI: "2023-12-01 10:00-11:00"
                slot_str = f"{row.starts_at.strftime('%Y-%m-%d %H:%M')}-{row.ends_at.strftime('%H:%M')}"
                if tid in busy_slots:
                    busy_slots[tid].append(slot_str)

    except Exception as e:
        print(f"⚠️ Błąd pobierania dostępności terapeutów: {e}")
        return {}

    return busy_slots


# ==========================================
# ASYSTENT GŁOSOWY - TRASY I API
# ==========================================

@app.route('/admin/super-panel-saas')
@superadmin_required
def super_panel_saas_page():
    """Strona główna centralnego zarządzania instancjami SaaS dla Super Admina."""
    return render_template('super_admin_companies.html')

@app.route('/api/superadmin/logs', methods=['GET'])
@superadmin_required
def superadmin_get_company_logs():
    """Zwraca rejestr logów systemowych filtrowany po firma_id dla wybranego podmiotu."""
    company_id = request.args.get('firma_id', type=int)
    limit = request.args.get('limit', 100, type=int)

    if not company_id:
        return jsonify({'error': 'Parametr firma_id jest wymagany.'}), 400

    try:
        with SessionLocal() as s:
            # Wyciągamy logi dla konkretnej firmy posortowane od najświeższych
            logs = (
                s.query(SystemLog)
                .filter(SystemLog.firma_id == company_id)
                .order_by(SystemLog.created_at.desc())
                .limit(limit)
                .all()
            )

            result = [{
                "id": l.id,
                "username": l.username if l.username else "System/Tło",
                "action": l.action,
                "details": l.details if l.details else "",
                "ip_address": l.ip_address if l.ip_address else "Brak IP",
                "created_at": l.created_at.strftime('%Y-%m-%d %H:%M:%S') if l.created_at else "-"
            } for l in logs]

            return jsonify(result), 200
    except Exception as e:
        print(f"❌ Błąd SuperAdmin Logs API: {e}")
        return jsonify({'error': str(e)}), 500

# 1. Trasa wyświetlająca stronę dla Admina
@app.route('/admin/voice-commands')
@login_required
def admin_voice_page():
    # Zabezpieczenie: tylko admin może modyfikować asystenta
    if not current_user.is_admin:
        flash("Brak uprawnień do edycji bazy komend asystenta.", "error")
        return redirect(url_for('dashboard')) # upewnij się, że masz funkcję dashboard (lub zmień na 'klient_panel')
    
    return render_template('admin_voice.html')


# 2. Endpoint pobierający komendy z bazy (dla skryptu w voice_assistant.html)
@app.route('/api/voice-commands', methods=['GET'])
@login_required
def get_voice_commands():
    try:
        with session_scope() as session:
            cmds = session.query(VoiceCommand).all()
            result = []
            for c in cmds:
                result.append({
                    'id': c.id,
                    'phrases': [p.strip().lower() for p in c.phrases.split(',')],
                    'action_type': c.action_type,
                    'target': c.target
                })
            return jsonify(result), 200
    except Exception as e:
        print(f"Błąd pobierania komend: {e}")
        return jsonify([]), 500


# 3. Endpoint zapisujący nową komendę z poziomu panelu Admina
@app.route('/api/admin/voice-commands', methods=['POST'])
@login_required
def save_voice_command():
    if not current_user.is_admin:
        return jsonify({'error': 'Brak uprawnień'}), 403

    data = request.get_json()
    action_type = data.get('action_type', 'navigate')
    target = data.get('target', '').strip()
    phrases = data.get('phrases', '').strip()
    force_save = data.get('force_save', False) # Flaga wymuszenia zapisu

    if not target or not phrases:
        return jsonify({'error': 'Wypełnij komendy i cel docelowy.'}), 400

    # Ostrzeżenie, jeśli admin podał adres URL, którego nie ma w systemie
    if action_type == 'navigate' and not force_save:
        valid_routes = [rule.rule for rule in app.url_map.iter_rules()]
        if target not in valid_routes and "<" not in target:
            return jsonify({'warning': f"Podany adres '{target}' nie istnieje w systemie."}), 200

    try:
        with session_scope() as session:
            new_cmd = VoiceCommand(
                phrases=phrases,
                action_type=action_type,
                target=target
            )
            session.add(new_cmd)
        return jsonify({'success': True, 'message': 'Komenda zapisana!'}), 201
    except Exception as e:
        return jsonify({'error': str(e)}), 500

# --- FUNKCJA POMOCNICZA (Dostosowana do client_unavailability) ---

@app.route('/api/v1/check-availability', methods=['POST'])
@login_required
def check_availability_before_planning():
    """
    Sprawdza czy klienci mają uzupełnioną dostępność w wybranym zakresie.
    Zwraca szczegółowe informacje o każdym kliencie.
    """
    try:
        data = request.json or {}
        client_ids = data.get('client_ids', [])
        start_date_str = data.get('start_date')
        end_date_str = data.get('end_date')
        current_firma_id = session.get('firma_id', 1)
        
        # Walidacja wejściowa
        if not client_ids:
            return jsonify({'error': 'Brak ID klientów'}), 400
        
        if not start_date_str or not end_date_str:
            return jsonify({'error': 'Brak zakresu dat'}), 400
        
        # Parsowanie dat
        try:
            start_date = datetime.strptime(start_date_str, '%Y-%m-%d').date()
            end_date = datetime.strptime(end_date_str, '%Y-%m-%d').date()
        except ValueError:
            return jsonify({'error': 'Nieprawidłowy format daty. Użyj YYYY-MM-DD'}), 400
        
        if start_date > end_date:
            return jsonify({'error': 'Data początkowa nie może być późniejsza niż końcowa'}), 400
        
        with session_scope() as session_db:
            # Pobierz klientów
            clients = session_db.query(Client).filter(
                Client.id.in_(client_ids),
                Client.firma_id == current_firma_id,
                Client.active == True
            ).all()
            
            if not clients:
                return jsonify({'error': 'Nie znaleziono aktywnych klientów o podanych ID'}), 404
            
            # Pobierz dostępność klientów
            unav_records = session_db.query(ClientUnavailability).filter(
                ClientUnavailability.client_id.in_(client_ids),
                ClientUnavailability.firma_id == current_firma_id
            ).all()
            
            # Mapowanie dostępności
            unav_map = {}
            for r in unav_records:
                if r.client_id not in unav_map:
                    unav_map[r.client_id] = []
                unav_map[r.client_id].append(r)
            
            results = []
            
            for client in clients:
                rules = unav_map.get(client.id, [])
                
                # Sprawdź czy klient ma ustawioną dostępność
                if not rules:
                    results.append({
                        'client_id': client.id,
                        'client_name': client.full_name,
                        'has_availability': False,
                        'has_valid_slots': False,
                        'available_days': [],
                        'message': 'Brak ustawionej dostępności - dodaj godziny dostępności'
                    })
                    continue
                
                # Sprawdź czy są wolne sloty w zakresie
                has_valid_slot = False
                available_days = []
                days_checked = 0
                
                curr = start_date
                while curr <= end_date:
                    # Sprawdzamy tylko dni robocze (Pon-Pt)
                    if curr.weekday() < 5:  # 0=Pon, 4=Pt
                        dow = curr.isoweekday()  # 1=Pon, 7=Niedz
                        days_checked += 1
                        
                        # Szukamy reguły dla tego dnia
                        day_rules = [r for r in rules if r.day_of_week == dow]
                        
                        if day_rules:
                            has_valid_slot = True
                            # Dodaj informacje o dostępnych godzinach
                            for rule in day_rules:
                                available_days.append({
                                    'date': curr.strftime('%Y-%m-%d'),
                                    'day_of_week': dow,
                                    'day_name': ['', 'Poniedziałek', 'Wtorek', 'Środa', 'Czwartek', 'Piątek', 'Sobota', 'Niedziela'][dow],
                                    'start_time': rule.start_time.strftime('%H:%M') if rule.start_time else '08:00',
                                    'end_time': rule.end_time.strftime('%H:%M') if rule.end_time else '16:00',
                                    'notes': rule.notes or ''
                                })
                    
                    curr += timedelta(days=1)
                
                # Jeśli nie sprawdziliśmy żadnych dni roboczych
                if days_checked == 0:
                    results.append({
                        'client_id': client.id,
                        'client_name': client.full_name,
                        'has_availability': True if rules else False,
                        'has_valid_slots': False,
                        'available_days': [],
                        'message': 'Brak dni roboczych w wybranym zakresie'
                    })
                    continue
                
                results.append({
                    'client_id': client.id,
                    'client_name': client.full_name,
                    'has_availability': True,
                    'has_valid_slots': has_valid_slot,
                    'available_days': available_days if has_valid_slot else [],
                    'message': 'OK' if has_valid_slot else 'Brak wolnych terminów w wybranym zakresie'
                })
            
            return jsonify({
                'results': results,
                'total_checked': len(results),
                'has_missing': any(not r['has_availability'] for r in results),
                'has_no_slots': any(r['has_availability'] and not r['has_valid_slots'] for r in results)
            }), 200
            
    except Exception as e:
        print(f"❌ Błąd w check-availability: {str(e)}")
        import traceback
        traceback.print_exc()
        return jsonify({
            'error': f'Wewnętrzny błąd serwera: {str(e)}'
        }), 500

@app.route('/api/clients/<int:client_id>/availability', methods=['GET'])
@login_required
def get_client_availability(client_id):
    """Pobiera dostępność konkretnego klienta"""
    try:
        current_firma_id = session.get('firma_id', 1)
        
        with session_scope() as session_db:
            # Sprawdź czy klient istnieje i należy do firmy
            client = session_db.query(Client).filter(
                Client.id == client_id,
                Client.firma_id == current_firma_id
            ).first()
            
            if not client:
                return jsonify({'error': 'Klient nie znaleziony'}), 404
            
            # Pobierz dostępność
            availability = session_db.query(ClientUnavailability).filter(
                ClientUnavailability.client_id == client_id,
                ClientUnavailability.firma_id == current_firma_id
            ).order_by(ClientUnavailability.day_of_week).all()
            
            # Formatuj dane
            result = []
            for av in availability:
                result.append({
                    'id': av.id,
                    'day_of_week': av.day_of_week,
                    'day_name': ['', 'Poniedziałek', 'Wtorek', 'Środa', 'Czwartek', 'Piątek', 'Sobota', 'Niedziela'][av.day_of_week],
                    'start_time': av.start_time.strftime('%H:%M') if av.start_time else None,
                    'end_time': av.end_time.strftime('%H:%M') if av.end_time else None,
                    'notes': av.notes or ''
                })
            
            return jsonify({
                'client_id': client_id,
                'client_name': client.full_name,
                'availability': result,
                'has_availability': len(result) > 0
            }), 200
            
    except Exception as e:
        print(f"❌ Błąd w get_client_availability: {str(e)}")
        return jsonify({'error': str(e)}), 500
        
def get_client_constraints(client_id):
    """
    Pobiera godziny NIEDOSTĘPNOŚCI klienta (np. szkoła).
    Zwraca string np.: "Poniedziałek 08:00-15:00, Wtorek 08:00-14:00"
    """
    try:
        with engine.connect() as conn:
            # ZMIANA: Tabela client_unavailability
            query = text("""
                SELECT day_of_week, start_time, end_time 
                FROM client_unavailability 
                WHERE client_id = :cid
            """)
            result = conn.execute(query, {"cid": client_id}).fetchall()

            if not result:
                return "Brak ograniczeń (dostępny cały dzień)"

            constraints = []
            for row in result:
                s_time = str(row.start_time)
                e_time = str(row.end_time)
                # Dodajemy informację, że to są godziny ZAJĘTE
                constraints.append(f"{row.day_of_week}: zajęte {s_time}-{e_time}")

            return ", ".join(constraints)

    except Exception as e:
        # print(f"⚠️ Błąd pobierania niedostępności: {e}")
        return None  # Zwracamy None tylko przy błędzie bazy (np. brak tabeli)


# --- REPLACE THE ENTIRE auto_plan_batch FUNCTION WITH THIS VERSION ---
# --- WKLEJ DO app.py ---



def get_available_days(availability, start_date, end_date):
    """Zwraca listę dni, w których klient jest dostępny"""
    from datetime import datetime, timedelta
    
    start = datetime.strptime(start_date, '%Y-%m-%d')
    end = datetime.strptime(end_date, '%Y-%m-%d')
    
    available_days = []
    current = start
    
    while current <= end:
        day_of_week = current.isoweekday()
        
        # Sprawdź czy klient jest dostępny tego dnia
        for slot in availability:
            if slot['day_of_week'] == day_of_week:
                available_days.append({
                    'date': current.strftime('%Y-%m-%d'),
                    'day_of_week': day_of_week,
                    'start_time': slot['start_time'],
                    'end_time': slot['end_time']
                })
                break
        
        current += timedelta(days=1)
    
    return available_days


@app.route('/api/v1/save-batch-plan', methods=['POST'])
def save_batch_plan():
    try:
        data = request.get_json()
        slots = data.get('slots', [])

        if not slots:
            return jsonify({"message": "Brak slotów do zapisania."}), 200

        # 1. POBIERAMY ADRES PORADNI RAZ (dla wydajności)
        clinic_addr = get_main_clinic_address()
        print(f"💾 Zapis {len(slots)} pakietów. Adres poradni: {clinic_addr}")

        saved_count = 0
        active_runs_cache = {}

        with engine.begin() as conn:
            for s in slots:
                try:
                    cid = s['client_id']
                    tid = s['therapist_id']
                    did = s.get('driver_id')

                    start_dt = datetime.strptime(s['starts_at'], '%Y-%m-%d %H:%M').replace(tzinfo=TZ)
                    end_dt = datetime.strptime(s['ends_at'], '%Y-%m-%d %H:%M').replace(tzinfo=TZ)

                    # Grupa Zdarzeń
                    group_uuid = uuid.uuid4()
                    conn.execute(text("""
                        INSERT INTO event_groups (id, client_id, label)
                        VALUES (:gid, :cid, :lbl)
                    """), {
                        "gid": group_uuid, "cid": cid, "lbl": f"AutoPlan {start_dt.strftime('%d.%m')}"
                    })

                    # Slot Terapii - TU UŻYWAMY clinic_addr ZAMIAST 'Poradnia'
                    session_id = uuid.uuid4()
                    conn.execute(text("""
                        INSERT INTO schedule_slots 
                        (id, group_id, client_id, therapist_id, kind, starts_at, ends_at, status, session_id, place_to)
                        VALUES (DEFAULT, :gid, :cid, :tid, 'therapy', :s, :e, 'planned', :sid, :addr)
                    """), {
                        "gid": group_uuid, "cid": cid, "tid": tid,
                        "s": start_dt, "e": end_dt, "sid": session_id,
                        "addr": clinic_addr  # <--- ZMIANA
                    })

                    # Transport
                    if did:
                        # PICKUP
                        p_start = start_dt - timedelta(minutes=30)
                        p_end = start_dt
                        pickup_key = (did, 'pickup', p_end)

                        if pickup_key in active_runs_cache:
                            run_id_pickup = active_runs_cache[pickup_key]
                        else:
                            run_id_pickup = uuid.uuid4()
                            active_runs_cache[pickup_key] = run_id_pickup

                        # Z Domu do Poradni (clinic_addr)
                        conn.execute(text("""
                            INSERT INTO schedule_slots 
                            (group_id, client_id, driver_id, kind, starts_at, ends_at, status, run_id, place_from, place_to)
                            VALUES (:gid, :cid, :did, 'pickup', :s, :e, 'planned', :rid, 'Dom', :addr)
                        """), {
                            "gid": group_uuid, "cid": cid, "did": did, "s": p_start, "e": p_end, "rid": run_id_pickup,
                            "addr": clinic_addr  # <--- ZMIANA (Cel podróży)
                        })

                        # DROPOFF
                        d_start = end_dt
                        d_end = end_dt + timedelta(minutes=30)
                        dropoff_key = (did, 'dropoff', d_start)

                        if dropoff_key in active_runs_cache:
                            run_id_dropoff = active_runs_cache[dropoff_key]
                        else:
                            run_id_dropoff = uuid.uuid4()
                            active_runs_cache[dropoff_key] = run_id_dropoff

                        # Z Poradni (clinic_addr) do Domu
                        conn.execute(text("""
                            INSERT INTO schedule_slots 
                            (group_id, client_id, driver_id, kind, starts_at, ends_at, status, run_id, place_from, place_to)
                            VALUES (:gid, :cid, :did, 'dropoff', :s, :e, 'planned', :rid, :addr, 'Dom')
                        """), {
                            "gid": group_uuid, "cid": cid, "did": did, "s": d_start, "e": d_end, "rid": run_id_dropoff,
                            "addr": clinic_addr  # <--- ZMIANA (Start podróży)
                        })

                    saved_count += 1

                except Exception as row_err:
                    print(f"⚠️ Błąd zapisu wiersza: {row_err}")
                    continue

        return jsonify({"message": f"Utworzono {saved_count} pakietów.", "saved": saved_count}), 200

    except Exception as e:
        print("❌ BŁĄD ZAPISU:")
        traceback.print_exc()
        return jsonify({"error": str(e)}), 500


@app.route('/api/v1/ai-plan-schedule', methods=['POST'])
def ai_plan_schedule():
    print("\n>>> AI PLAN SCHEDULE STARTED (Time Shift Enabled)")
    try:
        data = request.get_json()
        user_prompt = data.get('prompt')
        duration = data.get('duration', 60)
        client_id = data.get('clientId')
        needs_pickup = data.get('needsPickup', False)
        needs_dropoff = data.get('needsDropoff', False)

        # NOWE PARAMETRY: Ograniczenia czasowe
        min_time_str = data.get('min_time')  # np. "11:00" (Szukaj później niż X)
        max_time_str = data.get('max_time')  # np. "09:00" (Szukaj wcześniej niż X)

        # 1. DATY
        target_date_str = None
        import re
        date_match = re.search(r'\d{4}-\d{2}-\d{2}', user_prompt)
        if date_match:
            target_date_str = date_match.group(0)
        else:
            target_date_str = (datetime.now() + timedelta(days=1)).strftime('%Y-%m-%d')

        target_date = datetime.strptime(target_date_str, '%Y-%m-%d').date()

        day_name_eng = target_date.strftime('%A')
        days_map = {
            "Sunday": "Niedziela", "Monday": "Poniedziałek", "Tuesday": "Wtorek", "Wednesday": "Środa",
            "Thursday": "Czwartek", "Friday": "Piątek", "Saturday": "Sobota"
        }
        day_name_pl = days_map.get(day_name_eng)
        print(f"📅 Data: {target_date_str} | Zakres: {min_time_str or '8:00'} - {max_time_str or '18:00'}")

        # 2. NIEDOSTĘPNOŚĆ KLIENTA
        client_busy_hours = []
        with engine.connect() as conn:
            unav_rows = conn.execute(text("""
                SELECT day_of_week, start_time, end_time, notes 
                FROM client_unavailability WHERE client_id = :cid
            """), {"cid": client_id}).fetchall()

            for row in unav_rows:
                raw_day = row.day_of_week
                is_match = False
                if isinstance(raw_day, int):
                    if raw_day == target_date.weekday(): is_match = True
                elif isinstance(raw_day, str):
                    clean = raw_day.strip().lower()
                    if clean in [day_name_eng.lower(), day_name_pl.lower(), str(target_date.weekday())]:
                        is_match = True
                if is_match:
                    client_busy_hours.append({"start": row.start_time, "end": row.end_time, "reason": row.notes})

        # 3. KADRA
        candidate_ids = data.get('candidate_therapists', [])
        all_therapists = list(set([int(x) for x in candidate_ids if x]))
        if not all_therapists:
            with engine.connect() as conn:
                res = conn.execute(text("SELECT id FROM therapists WHERE active=true")).fetchall()
                all_therapists = [r.id for r in res]

        therapist_busy_map = get_availability_data(all_therapists, days_ahead=30)
        drivers_list, drivers_busy_map = get_driver_availability(days_ahead=30)
        all_driver_ids = [d['id'] for d in drivers_list]

        # --- FUNKCJE POMOCNICZE ---
        def is_time_blocked(start_t, end_t, busy_list):
            for busy in busy_list:
                try:
                    b_date_str, b_range = busy.split(' ', 1)
                    if b_date_str != target_date_str: continue
                    b_start_str, b_end_str = b_range.split('-')
                    b_start = datetime.strptime(b_start_str, "%H:%M").time()
                    b_end = datetime.strptime(b_end_str, "%H:%M").time()
                    if start_t < b_end and end_t > b_start: return True
                except:
                    continue
            return False

        def is_client_blocked(start_t, end_t):
            BUFFER = 30
            dummy = datetime(2000, 1, 1)
            slot_s = datetime.combine(dummy, start_t)
            slot_e = datetime.combine(dummy, end_t)
            for busy in client_busy_hours:
                busy_s = datetime.combine(dummy, busy['start']) - timedelta(minutes=BUFFER)
                busy_e = datetime.combine(dummy, busy['end']) + timedelta(minutes=BUFFER)
                if slot_s < busy_e and slot_e > busy_s: return True
            return False

        def find_driver_for_slot(start_time, end_time):
            for did in all_driver_ids:
                if not is_time_blocked(start_time, end_time, drivers_busy_map.get(did, [])):
                    return did
            return None

        # 4. AI PROMPT
        ai_proposal = None
        api_key = os.getenv("GOOGLE_AI_API_KEY")

        if api_key:
            try:
                genai.configure(api_key=api_key)
                model = genai.GenerativeModel('gemini-3.5-flash')

                busy_txt = ", ".join([f"{b['start']}-{b['end']}" for b in client_busy_hours])

                # Dodajemy ograniczenia czasowe do promptu
                time_constraint_txt = ""
                if min_time_str: time_constraint_txt += f"Wizyta musi się zacząć PO godzinie {min_time_str}. "
                if max_time_str: time_constraint_txt += f"Wizyta musi się zacząć PRZED godziną {max_time_str}. "

                prompt = f"""
                Zaplanuj wizytę ({target_date_str}). Czas trwania: {duration} min.
                {time_constraint_txt}
                KLIENT ZAJĘTY: {busy_txt} (plus 30min bufora!).

                WYMAGANIA TRANSPORTU: P={needs_pickup}, D={needs_dropoff}.

                KADRA (ID):
                - Terapeuci: {json.dumps(all_therapists)}
                - Kierowcy: {json.dumps(all_driver_ids)}

                ZAJĘTOŚĆ (HH:MM-HH:MM):
                - Terapeuci: {json.dumps(therapist_busy_map)}
                - Kierowcy: {json.dumps(drivers_busy_map)}

                Zwróć JSON. Format: {{ "status": "success", "proposals": [ ... ] }}
                """

                resp = model.generate_content(prompt, generation_config={"response_mime_type": "application/json"})
                ai_res = json.loads(resp.text)

                if ai_res.get("status") == "success":
                    for prop in ai_res.get("proposals", []):
                        th = prop.get("therapy", {})
                        s_str, e_str = th.get("start_time"), th.get("end_time")
                        tid = th.get("therapist_id")

                        if s_str and e_str and tid:
                            s_time = datetime.strptime(s_str, "%H:%M").time()
                            e_time = datetime.strptime(e_str, "%H:%M").time()

                            # Walidacja limitów min/max
                            if min_time_str and s_time <= datetime.strptime(min_time_str, "%H:%M").time(): continue
                            if max_time_str and s_time >= datetime.strptime(max_time_str, "%H:%M").time(): continue

                            # Walidacja kolizji
                            if not is_client_blocked(s_time, e_time) and not is_time_blocked(s_time, e_time,
                                                                                             therapist_busy_map.get(tid,
                                                                                                                    [])):
                                # Walidacja kierowców
                                pk = prop.get("pickup")
                                dp = prop.get("dropoff")
                                driver_ok = True
                                if needs_pickup and not pk: driver_ok = False
                                if needs_dropoff and not dp: driver_ok = False
                                if pk:
                                    pk_s = datetime.strptime(pk['start_time'], "%H:%M").time()
                                    pk_e = datetime.strptime(pk['end_time'], "%H:%M").time()
                                    if is_time_blocked(pk_s, pk_e,
                                                       drivers_busy_map.get(pk['driver_id'], [])): driver_ok = False
                                if dp:
                                    dp_s = datetime.strptime(dp['start_time'], "%H:%M").time()
                                    dp_e = datetime.strptime(dp['end_time'], "%H:%M").time()
                                    if is_time_blocked(dp_s, dp_e,
                                                       drivers_busy_map.get(dp['driver_id'], [])): driver_ok = False

                                if driver_ok:
                                    ai_proposal = prop
                                    break
            except Exception as e:
                print(f"⚠️ Błąd AI: {e}")

        # 5. ALGORYTM ZAPASOWY
        if not ai_proposal:
            print("🔄 Algorytm zapasowy...")

            # Domyślne ramy czasowe
            start_hour_dt = datetime.strptime(f"{target_date_str} 08:00", "%Y-%m-%d %H:%M")
            end_hour_dt = datetime.strptime(f"{target_date_str} 18:00", "%Y-%m-%d %H:%M")

            # Jeśli użytkownik kliknął "Później", zaczynamy od min_time
            if min_time_str:
                start_hour_dt = datetime.strptime(f"{target_date_str} {min_time_str}", "%Y-%m-%d %H:%M")

            # Jeśli użytkownik kliknął "Wcześniej", kończymy na max_time
            if max_time_str:
                end_hour_dt = datetime.strptime(f"{target_date_str} {max_time_str}", "%Y-%m-%d %H:%M")

            current_dt = start_hour_dt
            found = False

            # Jeśli szukamy "Wcześniej", lepiej iterować od tyłu?
            # Dla uproszczenia iterujemy normalnie w zadanym oknie.

            while current_dt + timedelta(minutes=duration) <= end_hour_dt:
                if found: break

                s_time = current_dt.time()
                e_time = (current_dt + timedelta(minutes=duration)).time()

                # Dodatkowe zabezpieczenie pętli (gdyby daty z inputu były dziwne)
                if min_time_str and s_time <= datetime.strptime(min_time_str, "%H:%M").time():
                    current_dt += timedelta(minutes=30)
                    continue

                if not is_client_blocked(s_time, e_time):
                    selected_tid = None
                    for tid in all_therapists:
                        if not is_time_blocked(s_time, e_time, therapist_busy_map.get(tid, [])):
                            selected_tid = tid
                            break

                    if selected_tid:
                        # Transport
                        pk_driver_id = None
                        dp_driver_id = None
                        can_schedule_transport = True

                        pk_start_time, pk_end_time = None, None
                        dp_start_time, dp_end_time = None, None

                        if needs_pickup:
                            pk_end_dt = current_dt
                            pk_start_dt = current_dt - timedelta(minutes=30)
                            pk_driver_id = find_driver_for_slot(pk_start_dt.time(), pk_end_dt.time())
                            if not pk_driver_id:
                                can_schedule_transport = False
                            else:
                                pk_start_time = pk_start_dt.strftime("%H:%M")
                                pk_end_time = pk_end_dt.strftime("%H:%M")

                        if needs_dropoff:
                            dp_start_dt = current_dt + timedelta(minutes=duration)
                            dp_end_dt = dp_start_dt + timedelta(minutes=30)
                            dp_driver_id = find_driver_for_slot(dp_start_dt.time(), dp_end_dt.time())
                            if not dp_driver_id:
                                can_schedule_transport = False
                            else:
                                dp_start_time = dp_start_dt.strftime("%H:%M")
                                dp_end_time = dp_end_dt.strftime("%H:%M")

                        if can_schedule_transport:
                            ai_proposal = {
                                "is_best_choice": True,
                                "label": "Znaleziono algorytmicznie",
                                "therapy": {
                                    "therapist_id": selected_tid,
                                    "date": target_date_str,
                                    "start_time": s_time.strftime("%H:%M"),
                                    "end_time": e_time.strftime("%H:%M"),
                                    "location": "Poradnia",
                                    "reason": "Dostępny termin."
                                },
                                "pickup": {"driver_id": pk_driver_id, "start_time": pk_start_time,
                                           "end_time": pk_end_time} if pk_driver_id else None,
                                "dropoff": {"driver_id": dp_driver_id, "start_time": dp_start_time,
                                            "end_time": dp_end_time} if dp_driver_id else None
                            }
                            found = True

                current_dt += timedelta(minutes=30)

        if ai_proposal:
            return jsonify({"status": "success", "proposals": [ai_proposal]})
        else:
            return jsonify({"status": "error", "reason": "Brak wolnych terminów w wybranym przedziale."}), 200

    except Exception as e:
        print(f"❌ Critical Error: {e}")
        traceback.print_exc()
        return jsonify({"status": "error", "reason": str(e)}), 500


@app.route('/api/v1/generate-monthly-plan', methods=['POST'])
@login_required
def generate_monthly_plan():
    """
    Generuje plan dla konkretnego klienta na cały miesiąc.
    Uwzględnia preferencje terapeutów i kierowców z historii.
    """
    try:
        data = request.json or {}
        client_id = data.get('client_id')
        year = data.get('year')
        month = data.get('month')
        active_days = data.get('active_days', [])
        global_start = data.get('global_start', '08:00')
        global_end = data.get('global_end', '18:00')
        current_firma_id = session.get('firma_id', 1)
        
        if not client_id or not year or not month:
            return jsonify({'error': 'Brak wymaganych parametrów'}), 400
        
        if not active_days:
            return jsonify({'error': 'Brak aktywnych dni'}), 400
        
        # Generuj dni miesiąca
        from calendar import monthrange
        _, last_day = monthrange(year, month)
        
        start_date = date(year, month, 1)
        end_date = date(year, month, last_day)
        
        with session_scope() as session_db:
            # Pobierz klienta
            client = session_db.query(Client).filter(
                Client.id == client_id,
                Client.firma_id == current_firma_id
            ).first()
            
            if not client:
                return jsonify({'error': 'Klient nie znaleziony'}), 404
            
            # Pobierz terapeutów i kierowców
            therapists = session_db.query(Therapist).filter_by(
                active=True, firma_id=current_firma_id
            ).all()
            drivers = session_db.query(Driver).filter_by(
                active=True, firma_id=current_firma_id
            ).all()
            
            # Pobierz historię preferencji
            # Najczęściej wybierani terapeuci
            th_sql = text("""
                SELECT therapist_id, COUNT(*) as cnt
                FROM schedule_slots
                WHERE client_id = :cid 
                    AND kind = 'therapy' 
                    AND status != 'cancelled'
                    AND firma_id = :fid
                GROUP BY therapist_id
                ORDER BY cnt DESC
            """)
            th_history = session_db.execute(th_sql, {
                "cid": client_id, 
                "fid": current_firma_id
            }).mappings().all()
            
            pref_therapists = [r['therapist_id'] for r in th_history]
            
            # Najczęściej wybierani kierowcy
            dr_sql = text("""
                SELECT driver_id, COUNT(*) as cnt
                FROM schedule_slots
                WHERE client_id = :cid 
                    AND kind IN ('pickup', 'dropoff') 
                    AND status != 'cancelled'
                    AND driver_id IS NOT NULL
                    AND firma_id = :fid
                GROUP BY driver_id
                ORDER BY cnt DESC
            """)
            dr_history = session_db.execute(dr_sql, {
                "cid": client_id, 
                "fid": current_firma_id
            }).mappings().all()
            
            pref_drivers = [r['driver_id'] for r in dr_history]
            
            # Pobierz istniejące rezerwacje w tym miesiącu
            busy_slots = session_db.query(ScheduleSlot).filter(
                ScheduleSlot.client_id == client_id,
                ScheduleSlot.status != 'cancelled',
                ScheduleSlot.starts_at >= datetime(year, month, 1),
                ScheduleSlot.starts_at <= datetime(year, month, last_day, 23, 59),
                ScheduleSlot.firma_id == current_firma_id
            ).all()
            
            busy_dates = {}
            for slot in busy_slots:
                date_key = slot.starts_at.date()
                if date_key not in busy_dates:
                    busy_dates[date_key] = []
                busy_dates[date_key].append((slot.starts_at, slot.ends_at))
            
            # Mapa aktywnych dni
            active_days_map = {}
            for day in active_days:
                active_days_map[day['day_of_week']] = day
            
            # Generuj sloty
            planned_slots = []
            warnings = []
            current_date = start_date
            
            while current_date <= end_date:
                dow = current_date.isoweekday()
                
                # Sprawdź czy dzień jest aktywny
                if dow in active_days_map:
                    day_config = active_days_map[dow]
                    
                    # Sprawdź czy już jest wizyta w tym dniu
                    if current_date in busy_dates:
                        warnings.append(f"📅 {current_date.strftime('%Y-%m-%d')} - już istnieje wizyta (pominięto)")
                        current_date += timedelta(days=1)
                        continue
                    
                    # Godziny dostępności
                    start_time = datetime.strptime(day_config['start_time'], '%H:%M').time()
                    end_time = datetime.strptime(day_config['end_time'], '%H:%M').time()
                    
                    # Globalne ograniczenia
                    global_start_t = datetime.strptime(global_start, '%H:%M').time()
                    global_end_t = datetime.strptime(global_end, '%H:%M').time()
                    
                    # Użyj późniejszego początku
                    final_start = max(start_time, global_start_t)
                    final_end = min(end_time, global_end_t)
                    
                    if final_start >= final_end:
                        warnings.append(f"⚠️ {current_date.strftime('%Y-%m-%d')} - konflikt godzin (pominięto)")
                        current_date += timedelta(days=1)
                        continue
                    
                    # Znajdź najlepszy termin (godzina 9:00 lub 14:00)
                    possible_times = [
                        datetime.combine(current_date, datetime.min.time()) + timedelta(hours=9),
                        datetime.combine(current_date, datetime.min.time()) + timedelta(hours=14),
                    ]
                    
                    best_slot = None
                    for visit_start in possible_times:
                        visit_end = visit_start + timedelta(minutes=45)
                        
                        # Sprawdź czy w godzinach dostępności
                        if visit_start.time() < final_start or visit_end.time() > final_end:
                            continue
                        
                        # Sprawdź konflikty
                        has_conflict = False
                        if current_date in busy_dates:
                            for b_start, b_end in busy_dates[current_date]:
                                if visit_start < b_end and visit_end > b_start:
                                    has_conflict = True
                                    break
                        
                        if has_conflict:
                            continue
                        
                        # Znajdź terapeutę
                        therapist_id = None
                        
                        # 1. Sprawdź preferowanego terapeutę z konfiguracji
                        if day_config.get('pref_therapist'):
                            therapist_id = day_config['pref_therapist']
                        # 2. Sprawdź historycznych preferowanych
                        elif pref_therapists:
                            therapist_id = pref_therapists[0]
                        # 3. Weź dowolnego
                        elif therapists:
                            therapist_id = therapists[0].id
                        
                        # Znajdź kierowcę
                        driver_id = None
                        if day_config.get('pref_driver'):
                            driver_id = day_config['pref_driver']
                        elif pref_drivers:
                            driver_id = pref_drivers[0]
                        elif drivers:
                            driver_id = drivers[0].id
                        
                        best_slot = {
                            'client_id': client_id,
                            'client_name': client.full_name,
                            'therapist_id': therapist_id,
                            'driver_id': driver_id,
                            'starts_at': visit_start.strftime('%Y-%m-%d %H:%M'),
                            'ends_at': visit_end.strftime('%Y-%m-%d %H:%M'),
                            'explanation': build_explanation(therapist_id, pref_therapists, driver_id, pref_drivers)
                        }
                        break
                    
                    if best_slot:
                        planned_slots.append(best_slot)
                        # Dodaj do busy_dates
                        if current_date not in busy_dates:
                            busy_dates[current_date] = []
                        busy_dates[current_date].append((
                            datetime.strptime(best_slot['starts_at'], '%Y-%m-%d %H:%M'),
                            datetime.strptime(best_slot['ends_at'], '%Y-%m-%d %H:%M')
                        ))
                    else:
                        warnings.append(f"⚠️ {current_date.strftime('%Y-%m-%d')} - nie znaleziono wolnego terminu")
                
                current_date += timedelta(days=1)
            
            # Podsumowanie
            warnings.append(f"✅ Zaplanowano {len(planned_slots)} wizyt dla {client.full_name}")
            
            return jsonify({
                'planned': planned_slots,
                'warnings': warnings,
                'summary': {
                    'total': len(planned_slots),
                    'client': client.full_name,
                    'month': f"{year}-{month:02d}"
                }
            }), 200
            
    except Exception as e:
        print(f"❌ Błąd generowania planu miesięcznego: {e}")
        import traceback
        traceback.print_exc()
        return jsonify({'error': str(e)}), 500

def build_explanation(therapist_id, pref_therapists, driver_id, pref_drivers):
    """Buduje wyjaśnienie dla slotu"""
    parts = []
    
    if therapist_id and pref_therapists and therapist_id == pref_therapists[0]:
        parts.append("⭐ Ulubiony terapeuta")
    elif therapist_id:
        parts.append("Dobór automatyczny")
    
    if driver_id and pref_drivers and driver_id == pref_drivers[0]:
        parts.append("🚌 Ulubiony kierowca")
    elif driver_id:
        parts.append("Kierowca przydzielony")
    else:
        parts.append("Bez transportu")
    
    return " - ".join(parts)


@app.route('/api/v1/auto-plan-monthly', methods=['POST'])
def auto_plan_monthly():
    import time as time_mod
    import math
    import calendar
    import random

    try:
        data = request.json
        client_id = int(data.get('clientId'))
        year = int(data.get('year'))
        month = int(data.get('month'))
        day_rules = data.get('day_rules', {})

        needs_pickup = data.get('needsPickup', False)
        needs_dropoff = data.get('needsDropoff', False)
        min_time_str = data.get('min_time', '08:00')
        max_time_str = data.get('max_time', '18:00')

        num_days = calendar.monthrange(year, month)[1]
        dates_to_plan = []

        # 1. Generowanie dat
        for day in range(1, num_days + 1):
            date_obj = date(year, month, day)
            weekday_str = str(date_obj.weekday())
            if weekday_str in day_rules:
                dates_to_plan.append(date_obj)

        with engine.connect() as conn:
            month_key_str = f"{year}-{month:02d}"
            client_addr = "Dom"  # Wartość domyślna
            try:
                c_row = conn.execute(
                    text("SELECT address FROM clients WHERE id = :cid"),
                    {"cid": client_id}
                ).mappings().first()

                if c_row and c_row['address']:
                    client_addr = c_row['address']
            except Exception as e:
                print(f"Błąd pobierania adresu klienta: {e}")

            # --- NOWOŚĆ: POBIERANIE ADRESU FIRMY (BAZY STARTOWEJ) ---
            company_addr = "Poradnia"  # Wartość domyślna

            try:
                # Pobieramy zarówno adres główny, jak i dodatkowy
                comp_row = conn.execute(text("""
                    SELECT 
                        ulica, numer_budynku, miasto,
                        adres_dodatkowy_ulica, adres_dodatkowy_numer, adres_dodatkowy_miasto
                    FROM firma LIMIT 1
                """)).mappings().first()

                if comp_row:
                    # Sprawdzamy, czy ustawiono adres dodatkowy (priorytet)
                    if comp_row['adres_dodatkowy_ulica'] and comp_row['adres_dodatkowy_miasto']:
                        ulica = comp_row['adres_dodatkowy_ulica']
                        nr = comp_row['adres_dodatkowy_numer'] or ''
                        miasto = comp_row['adres_dodatkowy_miasto']
                    else:
                        # Fallback do adresu głównego
                        ulica = comp_row['ulica'] or ''
                        nr = comp_row['numer_budynku'] or ''
                        miasto = comp_row['miasto'] or ''

                    # Formatowanie stringa: "ul. Prosta 10, Warszawa"
                    parts = [p for p in [ulica, nr, miasto] if p]
                    if parts:
                        company_addr = " ".join(parts)
                        # Opcjonalnie dodaj przecinek przed miastem jeśli są 3 elementy
                        if len(parts) >= 3:
                            company_addr = f"{ulica} {nr}, {miasto}"

            except Exception as e:
                print(f"⚠️ Błąd pobierania adresu firmy: {e}")
            # -----------------------------------------------------------

            # 2. Limity i Zużycie
            limit_row = conn.execute(
                text("SELECT minutes_quota FROM suo_allocations WHERE client_id=:cid AND month_key=:mk"),
                {"cid": client_id, "mk": month_key_str}).fetchone()
            limit_minutes = limit_row.minutes_quota if limit_row else 0

            used_row = conn.execute(text("""
                SELECT COALESCE(SUM(EXTRACT(EPOCH FROM (ends_at - starts_at))/60), 0) as used 
                FROM schedule_slots WHERE client_id=:cid AND kind='therapy' AND status!='cancelled'
                AND to_char(starts_at, 'YYYY-MM')=:mk
            """), {"cid": client_id, "mk": month_key_str}).fetchone()

            used_minutes = int(used_row.used) if used_row else 0
            remaining_minutes = limit_minutes - used_minutes

            # 3. Pobranie Zasobów
            all_therapists = [r.id for r in
                              conn.execute(text("SELECT id FROM therapists WHERE active=true")).fetchall()]
            all_drivers = [r.id for r in conn.execute(text("SELECT id FROM drivers WHERE active=true")).fetchall()]

            # 4. Mapy zajętości (istniejące w bazie)
            therapist_busy_map = get_availability_data(all_therapists, days_ahead=45)
            _, drivers_busy_map = get_driver_availability(days_ahead=45)

            unav_rows = conn.execute(
                text("SELECT day_of_week, start_time, end_time FROM client_unavailability WHERE client_id=:cid"),
                {"cid": client_id}).fetchall()

            # --- HELPERY ---
            def is_client_blocked_local(target_date, start_t, end_t):
                py_day_idx = target_date.weekday()
                expected_db_val = py_day_idx + 1  # Poprawka dla bazy 1-7

                dummy = datetime(2000, 1, 1)
                slot_s = datetime.combine(dummy, start_t)
                slot_e = datetime.combine(dummy, end_t)

                for r in unav_rows:
                    db_day = r.day_of_week
                    day_match = False
                    if isinstance(db_day, int):
                        if db_day == expected_db_val: day_match = True
                    elif isinstance(db_day, str):
                        if db_day.isdigit() and int(db_day) == expected_db_val:
                            day_match = True
                        else:
                            # Obsługa nazw tekstowych
                            pl = ["poniedziałek", "wtorek", "środa", "czwartek", "piątek", "sobota", "niedziela"]
                            if db_day.strip().lower() == pl[py_day_idx]: day_match = True

                    if day_match:
                        busy_s = datetime.combine(dummy, r.start_time) - timedelta(minutes=15)
                        busy_e = datetime.combine(dummy, r.end_time) + timedelta(minutes=15)
                        if slot_s < busy_e and slot_e > busy_s: return True
                return False

            def is_resource_blocked(date_str, start_t, end_t, busy_list):
                # Sprawdza kolizje z bazą danych (sloty już zapisane)
                for busy in busy_list:
                    try:
                        b_date, b_range = busy.split(' ', 1)
                        if b_date != date_str: continue
                        b_s_str, b_e_str = b_range.split('-')
                        b_s = datetime.strptime(b_s_str, "%H:%M").time()
                        b_e = datetime.strptime(b_e_str, "%H:%M").time()
                        if start_t < b_e and end_t > b_s: return True
                    except:
                        continue
                return False

        results = []

        # 5. GŁÓWNA PĘTLA PO DNIACH
        for current_date in dates_to_plan:
            date_str = current_date.strftime('%Y-%m-%d')
            weekday_str = str(current_date.weekday())

            rule = day_rules.get(weekday_str)
            if not rule: continue

            duration = int(rule['duration'])
            preferred_tid = rule['therapist_id']

            # --- ALGORYTM BALANCE ---
            daily_therapist_load = {tid: 0 for tid in all_therapists}

            day_result = {"date": date_str, "status": "failed", "proposal": None, "reason": ""}

            if remaining_minutes < duration:
                day_result["status"] = "limit"
                results.append(day_result)
                continue

            search_dt = datetime.strptime(f"{date_str} {min_time_str}", "%Y-%m-%d %H:%M")
            end_day_dt = datetime.strptime(f"{date_str} {max_time_str}", "%Y-%m-%d %H:%M")

            found_block = False

            # Szukanie slotu co 15 minut
            while search_dt + timedelta(minutes=duration) <= end_day_dt:
                slot_s = search_dt.time()
                slot_e = (search_dt + timedelta(minutes=duration)).time()

                # A. Dostępność klienta
                if is_client_blocked_local(current_date, slot_s, slot_e):
                    search_dt += timedelta(minutes=15)
                    continue

                # B. Wybór terapeuty (LOAD BALANCING)
                found_tid = None

                if preferred_tid:
                    # Jeśli wybrano konkretnego, sprawdzamy tylko jego
                    if not is_resource_blocked(date_str, slot_s, slot_e, therapist_busy_map.get(preferred_tid, [])):
                        found_tid = preferred_tid
                else:
                    sorted_candidates = sorted(
                        all_therapists,
                        key=lambda x: (daily_therapist_load.get(x, 0), random.random())
                    )

                    for tid in sorted_candidates:
                        # Sprawdź czy wolny w bazie
                        if not is_resource_blocked(date_str, slot_s, slot_e, therapist_busy_map.get(tid, [])):
                            found_tid = tid
                            break

                if found_tid:
                    # C. Transport
                    transport_ok = True
                    pk_info, dp_info = None, None

                    if needs_pickup:
                        pk_driver_id = None
                        pk_start = search_dt - timedelta(minutes=30)
                        # Tu też można dodać load balancing dla kierowców, na razie losowo
                        drivers_candidates = list(all_drivers)
                        random.shuffle(drivers_candidates)

                        for did in drivers_candidates:
                            if not is_resource_blocked(date_str, pk_start.time(), slot_s,
                                                       drivers_busy_map.get(did, [])):
                                pk_driver_id = did;
                                break
                        if pk_driver_id:
                            pk_info = {"driver_id": pk_driver_id, "start": pk_start.strftime("%H:%M"),
                                       "end": slot_s.strftime("%H:%M")}
                        else:
                            transport_ok = False

                    if needs_dropoff and transport_ok:
                        dp_driver_id = None
                        dp_end = search_dt + timedelta(minutes=duration) + timedelta(minutes=30)

                        drivers_candidates = list(all_drivers)
                        random.shuffle(drivers_candidates)  # Domyślnie losowo

                        # --- POPRAWKA: PRIORYTET DLA KIEROWCY Z PRZYWOZU ---
                        # Jeśli mamy kierowcę z przywozu (pk_driver_id), sprawdzamy go jako pierwszego.
                        # Algorytm 'is_resource_blocked' niżej sprawdzi, czy ma on wolne (czy nie ma "czegoś innego w planie").
                        if pk_driver_id and pk_driver_id in drivers_candidates:
                            drivers_candidates.remove(pk_driver_id)
                            drivers_candidates.insert(0, pk_driver_id)  # Wstaw na początek listy
                        # ---------------------------------------------------

                        for did in drivers_candidates:
                            if not is_resource_blocked(date_str, slot_e, dp_end.time(), drivers_busy_map.get(did, [])):
                                dp_driver_id = did;
                                break

                        if dp_driver_id:
                            dp_info = {"driver_id": dp_driver_id, "start": slot_e.strftime("%H:%M"),
                                       "end": dp_end.strftime("%H:%M")}
                        else:
                            transport_ok = False

                    # D. SUKCES
                    if transport_ok:
                        day_result["status"] = "success"
                        day_result["proposal"] = {
                            "block_start": slot_s.strftime("%H:%M"),
                            "block_end": slot_e.strftime("%H:%M"),
                            "slots": [
                                {"tid": found_tid, "start": slot_s.strftime("%H:%M"), "end": slot_e.strftime("%H:%M")}],
                            "pickup": pk_info, "dropoff": dp_info
                        }

                        # Aktualizacje liczników
                        remaining_minutes -= duration
                        daily_therapist_load[found_tid] += duration

                        # Dodajemy "wirtualną zajętość" do mapy
                        current_slot_str = f"{date_str} {slot_s.strftime('%H:%M')}-{slot_e.strftime('%H:%M')}"
                        if found_tid not in therapist_busy_map: therapist_busy_map[found_tid] = []
                        therapist_busy_map[found_tid].append(current_slot_str)

                        found_block = True
                        break

                search_dt += timedelta(minutes=15)

            if not found_block:
                day_result["reason"] = "Brak terminów (zajętość klienta/terapeuty/kierowcy)"
            results.append(day_result)

        return jsonify({
            "status": "success",
            "schedule": results,
            "budget_info": {"limit": limit_minutes / 60, "used_before": used_minutes / 60},
            "base_address": company_addr,  # <--- ZWRACAMY ADRES DO JS
            "client_address": client_addr
        })

    except Exception as e:
        print(f"❌ Error: {e}")
        import traceback
        traceback.print_exc()
        return jsonify({"status": "error", "error": str(e)}), 500


'''@app.route('/api/dashboard/stats')
def dashboard_stats():
    try:
        # 1. ODCZYT DATY Z FRONTENDU
        date_param = request.args.get('date')
        if date_param:
            target_date = datetime.strptime(date_param, '%Y-%m-%d').date()
        else:
            target_date = datetime.now().date()

        print(f"📊 Generowanie dashboardu dla daty: {target_date}")

        with engine.connect() as conn:
            # --- A. STATYSTYKI LICZBOWE ---
            stats_sql = text("""
                SELECT 
                    COUNT(*) FILTER (WHERE kind='therapy') as therapy_count,
                    COUNT(*) FILTER (WHERE kind IN ('pickup', 'dropoff')) as transport_count,
                    COUNT(DISTINCT client_id) as clients_count
                FROM schedule_slots 
                WHERE status != 'cancelled' 
                  AND date(starts_at) = :d
            """)
            stats = conn.execute(stats_sql, {"d": target_date}).fetchone()

            # --- B. LISTY TERAPEUTÓW ---
            therapists = conn.execute(text("SELECT id, full_name, phone FROM therapists WHERE active=true")).fetchall()

            busy_therapists = []
            free_therapists = []
            absent_therapists = []

            # SQL: Używamy aliasu "slot_id" dla s.id
            th_slots = conn.execute(text("""
                SELECT s.therapist_id, s.id as slot_id, s.starts_at, s.ends_at, c.full_name as client_name, c.id as client_id, s.status
                FROM schedule_slots s
                JOIN clients c ON s.client_id = c.id
                WHERE s.kind='therapy' AND s.status != 'cancelled' 
                  AND date(s.starts_at) = :d
                ORDER BY s.starts_at ASC
            """), {"d": target_date}).fetchall()

            # Grupujemy sloty po terapeucie
            slots_by_th = {}
            for s in th_slots:
                if s.therapist_id not in slots_by_th: slots_by_th[s.therapist_id] = []
                slots_by_th[s.therapist_id].append({
                    "time_display": f"{s.starts_at.strftime('%H:%M')}-{s.ends_at.strftime('%H:%M')}",
                    "client_name": s.client_name,
                    "slot_id": s.slot_id,  # <--- POPRAWKA (było s.id)
                    "client_id": s.client_id,
                    "status": s.status,
                    "start_iso": s.starts_at.isoformat(),
                    "end_iso": s.ends_at.isoformat()
                })

            for t in therapists:
                if t.id in slots_by_th:
                    busy_therapists.append({
                        "name": t.full_name,
                        "tasks": slots_by_th[t.id]
                    })
                else:
                    free_therapists.append({
                        "name": t.full_name,
                        "phone": t.phone
                    })

            # --- C. LISTY KIEROWCÓW ---
            drivers = conn.execute(text("SELECT id, full_name, phone FROM drivers WHERE active=true")).fetchall()
            busy_drivers = []
            free_drivers = []
            absent_drivers = []

            dr_slots = conn.execute(text("""
                SELECT s.driver_id, s.id as slot_id, s.starts_at, s.kind, 
                       CASE WHEN s.client_id IS NOT NULL THEN c.full_name ELSE 'Inne' END as client_name
                FROM schedule_slots s
                LEFT JOIN clients c ON s.client_id = c.id
                WHERE s.kind IN ('pickup', 'dropoff') AND s.status != 'cancelled'
                  AND date(s.starts_at) = :d
                ORDER BY s.starts_at ASC
            """), {"d": target_date}).fetchall()

            slots_by_dr = {}
            for s in dr_slots:
                did = s.driver_id
                if did not in slots_by_dr: slots_by_dr[did] = []
                slots_by_dr[did].append({
                    "time": s.starts_at.strftime('%H:%M'),
                    "client": s.client_name,
                    "kind": s.kind,
                    "slot_id": s.slot_id  # Tutaj było dobrze, ale upewniamy się
                })

            for d in drivers:
                if d.id in slots_by_dr:
                    busy_drivers.append({"name": d.full_name, "tasks": slots_by_dr[d.id]})
                else:
                    free_drivers.append({"name": d.full_name, "phone": d.phone})

            return jsonify({
                "therapy_count": stats.therapy_count if stats else 0,
                "transport_count": stats.transport_count if stats else 0,
                "clients_today": stats.clients_count if stats else 0,
                "busy_therapists": busy_therapists,
                "free_therapists": free_therapists,
                "absent_therapists": absent_therapists,
                "busy_drivers": busy_drivers,
                "free_drivers": free_drivers,
                "absent_drivers": absent_drivers
            })

    except Exception as e:
        print(f"❌ Dashboard Error: {e}")
        import traceback
        traceback.print_exc()
        return jsonify({"error": str(e)}), 500'''


@app.route('/api/driver/mileage-report', methods=['GET'])
@driver_required
def get_driver_mileage_report():
    """
    Generuje raport kilometrówki dla zalogowanego kierowcy na podany miesiąc.
    """
    driver_id = session.get('driver_id')
    month_str = request.args.get('month')  # Format: "YYYY-MM"

    if not driver_id:
        return jsonify({'error': 'Błąd sesji kierowcy'}), 403

    if not month_str:
        # Domyślnie bieżący miesiąc
        month_str = datetime.now().strftime('%Y-%m')

    try:
        year, month = map(int, month_str.split('-'))
    except ValueError:
        return jsonify({'error': 'Nieprawidłowy format daty'}), 400

    try:
        with engine.connect() as conn:
            # Pobieramy trasy (pickup/dropoff) zrealizowane lub zaplanowane
            # Sortujemy chronologicznie
            sql = text("""
                SELECT 
                    ss.starts_at,
                    ss.place_from,
                    ss.place_to,
                    ss.distance_km,
                    ss.status,
                    c.full_name as client_name
                FROM schedule_slots ss
                LEFT JOIN clients c ON ss.client_id = c.id
                WHERE ss.driver_id = :did
                  AND ss.kind IN ('pickup', 'dropoff')
                  AND EXTRACT(YEAR FROM ss.starts_at) = :year
                  AND EXTRACT(MONTH FROM ss.starts_at) = :month
                  AND ss.status != 'cancelled'  -- Pomijamy anulowane
                ORDER BY ss.starts_at ASC
            """)

            rows = conn.execute(sql, {"did": driver_id, "year": year, "month": month}).mappings().all()

            report_data = []
            total_km = 0.0
            total_trips = 0

            for r in rows:
                dist = float(r['distance_km'] or 0.0)

                # Sumujemy tylko jeśli trasa ma dystans
                total_km += dist
                total_trips += 1

                report_data.append({
                    "date": r['starts_at'].strftime('%Y-%m-%d'),
                    "time": r['starts_at'].strftime('%H:%M'),
                    "client": r['client_name'],
                    "route": f"{r['place_from']} ➝ {r['place_to']}",
                    "distance": round(dist, 2),
                    "status": r['status']
                })

            return jsonify({
                "month": month_str,
                "trips": report_data,
                "summary": {
                    "total_km": round(total_km, 2),
                    "total_trips": total_trips,
                    "rate_per_km": 1.15  # Przykładowa stawka, możesz pobrać z bazy
                }
            }), 200

    except Exception as e:
        print(f"Błąd raportu kierowcy: {e}")
        import traceback
        traceback.print_exc()
        return jsonify({'error': str(e)}), 500


# --- DASHBOARD API ---
# --- DASHBOARD API ---
@app.route('/api/dashboard/stats', methods=['GET'])
@login_required
def get_dashboard_stats():
    """
    Zwraca statystyki dla Dashboardu (Centrum Dowodzenia) z pełną izolacją Multi-tenant.
    Filtruje wszystkie liczniki, terapeutów, kierowców i nieobecności po firma_id z sesji.
    """
    date_str = request.args.get('date')
    if date_str:
        try:
            target_date = datetime.strptime(date_str, '%Y-%m-%d').date()
        except ValueError:
            target_date = datetime.now(TZ).date()
    else:
        target_date = datetime.now(TZ).date()

    first_day_of_month = target_date.replace(day=1)
    if first_day_of_month.month == 12:
        last_day_of_month = first_day_of_month.replace(year=first_day_of_month.year + 1, month=1) - timedelta(days=1)
    else:
        last_day_of_month = first_day_of_month.replace(month=first_day_of_month.month + 1) - timedelta(days=1)

    try:
        # --- POBIERAMY ID FIRMY Z SESJI ZALOGOWANEGO UŻYTKOWNIKA ---
        current_firma_id = session.get('firma_id', 1)

        with engine.connect() as conn:
            # === CZĘŚĆ 1: OGÓLNE STATYSTYKI (Zabezpieczone firma_id) ===
            stats_row = conn.execute(text("""
                SELECT 
                    (SELECT COUNT(*) FROM schedule_slots WHERE kind='therapy' AND status != 'cancelled' AND date(starts_at AT TIME ZONE 'Europe/Warsaw') = :d AND firma_id = :firma_id) +
                    (SELECT COUNT(*) FROM tus_sessions WHERE session_date = :d AND firma_id = :firma_id) as therapy_count,
                    
                    (SELECT COUNT(*) FROM schedule_slots WHERE kind IN ('pickup', 'dropoff') AND status != 'cancelled' AND date(starts_at AT TIME ZONE 'Europe/Warsaw') = :d AND firma_id = :firma_id) as transport_count,
                    
                    (SELECT COUNT(*) FROM clients WHERE active = true AND firma_id = :firma_id) as clients_count
            """), {"d": target_date, "firma_id": current_firma_id}).mappings().first()

            # === CZĘŚĆ 2: TERAPEUCI (Zabezpieczone firma_id) ===
            all_therapists = conn.execute(text("""
                SELECT id, full_name, phone FROM therapists WHERE active=true AND firma_id = :firma_id
            """), {"firma_id": current_firma_id}).mappings().all()

            th_absences = conn.execute(text("""
                SELECT person_id, reason, start_date, end_date, id as absence_id
                FROM absences
                WHERE person_type = 'therapist' AND status != 'cancelled' AND firma_id = :firma_id
                  AND start_date <= :last_day AND end_date >= :first_day
                ORDER BY start_date ASC
            """), {"first_day": first_day_of_month, "last_day": last_day_of_month, "firma_id": current_firma_id}).mappings().all()

            absent_today_th_ids = {
                a['person_id'] for a in th_absences 
                if a['start_date'] <= target_date <= a['end_date']
            }

            th_absences_map = {}
            for a in th_absences:
                if a['person_id'] not in th_absences_map: th_absences_map[a['person_id']] = []
                th_absences_map[a['person_id']].append(a)

            th_slots_sql = text("""
                WITH all_tasks AS (
                    SELECT ss.therapist_id, ss.id as slot_id, ss.starts_at, ss.ends_at,
                           c.full_name as client_name, c.id as client_id, ss.status,
                           FALSE as is_tus, NULL as group_name, NULL::json as members
                    FROM schedule_slots ss
                    JOIN clients c ON ss.client_id = c.id
                    WHERE ss.kind = 'therapy' AND ss.status != 'cancelled' AND ss.firma_id = :firma_id
                      AND date(ss.starts_at AT TIME ZONE 'Europe/Warsaw') = :d
                    
                    UNION ALL
                    
                    SELECT g.therapist_id, s.id as slot_id,
                           (s.session_date::timestamp + COALESCE(s.session_time, '00:00:00')::time) AT TIME ZONE 'Europe/Warsaw' AS starts_at,
                           (s.session_date::timestamp + COALESCE(s.session_time, '00:00:00')::time + INTERVAL '60 minutes') AT TIME ZONE 'Europe/Warsaw' AS ends_at,
                           NULL as client_name, NULL as client_id, 'planned' as status,
                           TRUE as is_tus, g.name as group_name,
                           (SELECT json_agg(json_build_object('id', c.id, 'name', c.full_name))
                            FROM tus_group_members gm JOIN clients c ON c.id = gm.client_id
                            WHERE gm.group_id = g.id AND gm.is_active = true AND gm.firma_id = :firma_id) as members
                    FROM tus_sessions s
                    JOIN tus_groups g ON s.group_id = g.id
                    WHERE s.session_date = :d AND g.therapist_id IS NOT NULL AND s.firma_id = :firma_id

                    UNION ALL
                    
                    SELECT g.assistant_therapist_id as therapist_id, s.id as slot_id,
                           (s.session_date::timestamp + COALESCE(s.session_time, '00:00:00')::time) AT TIME ZONE 'Europe/Warsaw' AS starts_at,
                           (s.session_date::timestamp + COALESCE(s.session_time, '00:00:00')::time + INTERVAL '60 minutes') AT TIME ZONE 'Europe/Warsaw' AS ends_at,
                           NULL as client_name, NULL as client_id, 'planned' as status,
                           TRUE as is_tus, g.name as group_name,
                           (SELECT json_agg(json_build_object('id', c.id, 'name', c.full_name))
                            FROM tus_group_members gm JOIN clients c ON c.id = gm.client_id
                            WHERE gm.group_id = g.id AND gm.is_active = true AND gm.firma_id = :firma_id) as members
                    FROM tus_sessions s
                    JOIN tus_groups g ON s.group_id = g.id
                    WHERE s.session_date = :d AND g.assistant_therapist_id IS NOT NULL AND s.firma_id = :firma_id
                )
                SELECT * FROM all_tasks ORDER BY starts_at ASC
            """)
            
            th_slots = conn.execute(th_slots_sql, {"d": target_date, "firma_id": current_firma_id}).mappings().all()

            th_slots_map = {}
            for s in th_slots:
                if s['therapist_id'] not in th_slots_map: th_slots_map[s['therapist_id']] = []
                th_slots_map[s['therapist_id']].append(s)

            busy_therapists = []
            free_therapists = []
            absent_therapists_list = []

            for th in all_therapists:
                if th['id'] in th_absences_map:
                    for ab in th_absences_map[th['id']]:
                        s_date = ab['start_date'].strftime('%d.%m')
                        e_date = ab['end_date'].strftime('%d.%m')
                        period_str = s_date if s_date == e_date else f"{s_date} - {e_date}"
                        absent_therapists_list.append({
                            'id': th['id'], 'name': th['full_name'],
                            'reason': ab['reason'], 'period': period_str,
                            'absence_id': ab['absence_id']
                        })

                if th['id'] in th_slots_map:
                    tasks = []
                    for slot in th_slots_map[th['id']]:
                        start_iso = slot['starts_at'].astimezone(TZ).isoformat() if slot['starts_at'].tzinfo else slot['starts_at'].replace(tzinfo=TZ).isoformat()
                        end_iso = slot['ends_at'].astimezone(TZ).isoformat() if slot['ends_at'].tzinfo else slot['ends_at'].replace(tzinfo=TZ).isoformat()
                        tasks.append({
                            'slot_id': slot['slot_id'],
                            'time_display': slot['starts_at'].strftime('%H:%M'),
                            'start_iso': start_iso,
                            'end_iso': end_iso,
                            'client_name': slot['client_name'],
                            'client_id': slot['client_id'],
                            'status': slot['status'],
                            'is_tus': slot['is_tus'],
                            'group_name': slot['group_name'],
                            'members': slot['members'] or []
                        })
                    busy_therapists.append({'id': th['id'], 'name': th['full_name'], 'tasks': tasks})
                elif th['id'] not in absent_today_th_ids:
                    free_therapists.append({'id': th['id'], 'name': th['full_name'], 'phone': th['phone']})

            # === CZĘŚĆ 3: KIEROWCY (Zabezpieczone firma_id) ===
            all_drivers = conn.execute(text("SELECT id, full_name, phone FROM drivers WHERE active=true AND firma_id = :firma_id"), {"firma_id": current_firma_id}).mappings().all()

            dr_absences = conn.execute(text("""
                SELECT driver_id, reason, start_date, end_date, id as absence_id
                FROM driver_absences
                WHERE start_date <= :last_day AND end_date >= :first_day AND firma_id = :firma_id
                ORDER BY start_date ASC
            """), {"first_day": first_day_of_month, "last_day": last_day_of_month, "firma_id": current_firma_id}).mappings().all()

            absent_today_dr_ids = {
                a['driver_id'] for a in dr_absences 
                if a['start_date'] <= target_date <= a['end_date']
            }

            dr_absences_map = {}
            for a in dr_absences:
                if a['driver_id'] not in dr_absences_map: dr_absences_map[a['driver_id']] = []
                dr_absences_map[a['driver_id']].append(a)

            dr_slots = conn.execute(text("""
                SELECT s.driver_id, s.id as slot_id, s.starts_at, s.kind, 
                       CASE WHEN s.client_id IS NOT NULL THEN c.full_name ELSE 'Inne' END as client_name
                FROM schedule_slots s
                LEFT JOIN clients c ON s.client_id = c.id
                WHERE s.kind IN ('pickup', 'dropoff') AND s.status != 'cancelled' AND s.firma_id = :firma_id
                  AND date(s.starts_at AT TIME ZONE 'Europe/Warsaw') = :d
                ORDER BY s.starts_at ASC
            """), {"d": target_date, "firma_id": current_firma_id}).mappings().all()

            dr_slots_map = {}
            for s in dr_slots:
                if s['driver_id'] not in dr_slots_map: dr_slots_map[s['driver_id']] = []
                dr_slots_map[s['driver_id']].append(s)

            busy_drivers = []
            free_drivers = []
            absent_drivers_list = []

            for dr in all_drivers:
                if dr['id'] in dr_absences_map:
                    for ab in dr_absences_map[dr['id']]:
                        s_date = ab['start_date'].strftime('%d.%m')
                        e_date = ab['end_date'].strftime('%d.%m')
                        period_str = s_date if s_date == e_date else f"{s_date} - {e_date}"
                        absent_drivers_list.append({
                            'id': dr['id'], 'name': dr['full_name'],
                            'reason': ab['reason'], 'period': period_str,
                            'absence_id': ab['absence_id']
                        })

                if dr['id'] in dr_slots_map:
                    tasks = [{'slot_id': s['slot_id'], 'time': s['starts_at'].strftime('%H:%M'), 'client': s['client_name'], 'kind': s['kind']} for s in dr_slots_map[dr['id']]]
                    busy_drivers.append({'id': dr['id'], 'name': dr['full_name'], 'tasks': tasks})
                elif dr['id'] not in absent_today_dr_ids:
                    free_drivers.append({'id': dr['id'], 'name': dr['full_name'], 'phone': dr['phone']})

            return jsonify({
                'therapy_count': stats_row['therapy_count'] if stats_row else 0,
                'transport_count': stats_row['transport_count'] if stats_row else 0,
                'clients_today': stats_row['clients_count'] if stats_row else 0,
                'busy_therapists': busy_therapists,
                'free_therapists': free_therapists,
                'absent_therapists': absent_therapists_list,
                'busy_drivers': busy_drivers,
                'free_drivers': free_drivers,
                'absent_drivers': absent_drivers_list
            }), 200

    except Exception as e:
        print(f"❌ Dashboard Error: {e}")
        import traceback
        traceback.print_exc()
        return jsonify({'error': str(e)}), 500


def find_cached_distance(conn, origin, destination):
    """
    Sprawdza w bazie danych, czy ta trasa była już kiedyś liczona.
    Zwraca float (km) lub None.
    """
    try:
        # Normalizacja stringów (usuwanie spacji, małe litery) dla lepszego dopasowania
        if not origin or not destination: return None

        # Szukamy dowolnego slotu z taką samą parą adresów i wpisanym dystansem > 0
        query = text("""
            SELECT distance_km 
            FROM schedule_slots 
            WHERE place_from = :orig 
              AND place_to = :dest 
              AND distance_km > 0 
            LIMIT 1
        """)

        result = conn.execute(query, {"orig": origin, "dest": destination}).scalar()

        if result is not None:
            return float(result)
        return None
    except Exception:
        return None


@app.route('/api/debug/force-update-client-routes/<int:client_id>', methods=['POST'])
@login_required
def force_update_client_routes(client_id):
    """
    Wymusza aktualizację tras z POTRÓJNYM cachem, aby oszczędzać budżet Google API.
    """
    try:
        with engine.begin() as conn:
            # 1. Pobierz dane klienta
            client = conn.execute(
                text("SELECT address, full_name FROM clients WHERE id = :cid"),
                {"cid": client_id}
            ).mappings().first()

            if not client or not client['address']:
                return jsonify({"error": "Klient nie ma wpisanego adresu w profilu."}), 400

            correct_address = client['address'].strip()
            print(f"🔧 Optymalizacja tras dla: {client['full_name']} -> {correct_address}")

            # 2. Pobierz przyszłe sloty
            slots = conn.execute(text("""
                SELECT id, kind, place_from, place_to 
                FROM schedule_slots
                WHERE client_id = :cid 
                  AND kind IN ('pickup', 'dropoff')
                  AND status = 'planned'
                  AND starts_at > NOW()
            """), {"cid": client_id}).mappings().all()

            updated_count = 0
            api_calls = 0
            cache_hits = 0
            errors = []

            # --- LOCAL CACHE (Pamięć podręczna dla tej pętli) ---
            # Zapobiega pytaniu Google 10 razy o to samo w ciągu jednej sekundy
            # Klucz: "Skąd|Dokąd", Wartość: dystans_km
            session_cache = {}

            for slot in slots:
                slot_id = slot['id']
                origin = slot['place_from']
                destination = slot['place_to']

                # Ustalanie nowych adresów
                if slot['kind'] == 'pickup':
                    origin = correct_address
                    # destination (Poradnia) bez zmian
                elif slot['kind'] == 'dropoff':
                    destination = correct_address
                    # origin (Poradnia) bez zmian

                dist_km = 0.0
                error_msg = None
                source_info = "API"  # Do logowania skąd wzięliśmy dane

                # === LINIA OBRONY 1: Logika ===
                if origin.lower().strip() == destination.lower().strip():
                    dist_km = 0.0
                    source_info = "SameAddress"

                else:
                    # Klucz do cache
                    route_key = f"{origin.strip()}|{destination.strip()}"

                    # === LINIA OBRONY 2: Local Cache (W tej pętli) ===
                    if route_key in session_cache:
                        dist_km = session_cache[route_key]
                        source_info = "LocalCache"
                        cache_hits += 1

                    else:
                        # === LINIA OBRONY 3: DB Cache (Historia) ===
                        # Sprawdzamy, czy w bazie jest już taki dystans z przeszłości
                        cached_db = find_cached_distance(conn, origin, destination)

                        if cached_db is not None:
                            dist_km = cached_db
                            session_cache[route_key] = dist_km  # Zapisz do local cache na przyszłość
                            source_info = "DBCache"
                            cache_hits += 1

                        else:
                            # === OSTATECZNOŚĆ: Google API ===
                            # Dopiero teraz płacimy za zapytanie
                            print(f"   💸 Zapytanie do Google: {origin} -> {destination}")
                            dist_result = get_route_distance(origin, destination)
                            api_calls += 1

                            if isinstance(dist_result, (float, int)):
                                dist_km = float(dist_result)
                                session_cache[route_key] = dist_km  # Zapamiętaj wynik!
                            elif isinstance(dist_result, tuple):
                                dist_km, error_msg = dist_result
                                if not error_msg: session_cache[route_key] = dist_km
                            elif dist_result is None:
                                error_msg = "Google API zwróciło brak danych"

                if error_msg:
                    errors.append(f"Slot {slot_id}: {error_msg}")
                else:
                    print(f"   -> Slot {slot_id}: {dist_km} km [{source_info}]")

                # Zapis do bazy
                conn.execute(text("""
                    UPDATE schedule_slots 
                    SET place_from = :orig, 
                        place_to = :dest, 
                        distance_km = :dist
                    WHERE id = :sid
                """), {
                    "orig": origin,
                    "dest": destination,
                    "dist": dist_km,
                    "sid": slot_id
                })
                updated_count += 1

            # Podsumowanie
            msg = f"Zaktualizowano {updated_count} kursów."
            msg += f" (Użyto Google API: {api_calls} razy, Cache: {cache_hits} razy)."

            if errors:
                msg += f" Błędy: {len(errors)}."

            return jsonify({"message": msg, "success": True}), 200

    except Exception as e:
        print(f"Błąd force_update: {e}")
        import traceback
        traceback.print_exc()
        return jsonify({"error": str(e)}), 500


def generate_safe_username(full_name, existing_usernames):
    """Generuje unikalny login: Jan Kowalski -> j.kowalski"""
    if not full_name:
        return "user"

    # Usuń polskie znaki i zamień na małe litery
    clean_name = unidecode.unidecode(full_name).lower()
    parts = clean_name.split()

    if len(parts) >= 2:
        base_login = f"{parts[0][0]}.{parts[-1]}"  # j.kowalski
    else:
        base_login = clean_name  # jan

    # Zapewnij unikalność (np. j.kowalski, j.kowalski2)
    login = base_login
    counter = 2
    while login in existing_usernames:
        login = f"{base_login}{counter}"
        counter += 1

    return login


@app.post('/api/admin/import-therapists-as-users')
@login_required
def import_therapists_as_users():
    """Tworzy konta użytkowników dla terapeutów, którzy ich nie mają"""
    try:
        created_count = 0
        with session_scope() as db_session:
            # 1. Pobierz wszystkich terapeutów i użytkowników
            therapists = db_session.query(Therapist).filter_by(active=True).all()
            existing_users = db_session.query(User).all()

            # Zbiór zajętych loginów i ID powiązanych terapeutów
            existing_usernames = {u.username for u in existing_users}
            linked_therapist_ids = {u.therapist_id for u in existing_users if u.therapist_id}

            for therapist in therapists:
                # Jeśli ten terapeuta ma już powiązane konto - pomiń
                if therapist.id in linked_therapist_ids:
                    continue

                # Generuj login
                new_username = generate_safe_username(therapist.full_name, existing_usernames)

                # Dodaj do zbioru, żeby kolejny w pętli nie dostał tego samego
                existing_usernames.add(new_username)

                # Twórz usera
                new_user = User(
                    username=new_username,
                    password_hash=generate_password_hash("start123"),  # Domyślne hasło
                    full_name=therapist.full_name,
                    is_admin=False,
                    is_secretariat=False,
                    therapist_id=therapist.id,  # KLUCZOWE: Powiązanie tabel
                    driver_id=None
                )
                db_session.add(new_user)
                created_count += 1

            db_session.commit()

        return jsonify({
            "success": True,
            "message": f"Utworzono {created_count} nowych kont dla terapeutów.",
            "count": created_count
        })

    except Exception as e:
        print(f"Błąd importu terapeutów: {e}")
        return jsonify({"error": str(e)}), 500


@app.route('/api/drivers/<int:driver_id>/absences', methods=['GET', 'POST'])
@login_required
def manage_driver_absences(driver_id):
    current_firma_id = session.get('firma_id', 1)
    
    # --- SPRAWDŹ CZY KIEROWCA NALEŻY DO FIRMY ---
    with SessionLocal() as s:
        driver = s.query(Driver).filter_by(id=driver_id, firma_id=current_firma_id).first()
        if not driver:
            return jsonify({'error': 'Brak dostępu do tego kierowcy'}), 403

    if request.method == 'GET':
        with session_scope() as db_session:
            # Dodano filtr .filter_by(..., firma_id=current_firma_id)
            absences = db_session.query(DriverAbsence).filter_by(
                driver_id=driver_id, 
                firma_id=current_firma_id
            ).order_by(DriverAbsence.start_date.desc()).all()
            
            return jsonify([{
                'id': a.id, 
                'start_date': a.start_date.isoformat(),
                'end_date': a.end_date.isoformat(), 
                'reason': a.reason, 
                'comment': a.comment
            } for a in absences])

    if request.method == 'POST':
        data = request.get_json()
        try:
            start = datetime.strptime(data['start_date'], '%Y-%m-%d').date()
            end = datetime.strptime(data['end_date'], '%Y-%m-%d').date()

            with session_scope() as db_session:
                # Sprawdź czy kierowca należy do firmy (ponownie dla bezpieczeństwa)
                driver_check = db_session.query(Driver).filter_by(
                    id=driver_id, 
                    firma_id=current_firma_id
                ).first()
                
                if not driver_check:
                    return jsonify({'error': 'Brak dostępu do tego kierowcy'}), 403
                
                new_absence = DriverAbsence(
                    driver_id=driver_id,
                    start_date=start,
                    end_date=end,
                    reason=data['reason'],
                    comment=data.get('comment', ''),
                    firma_id=current_firma_id  # <--- POWIĄZANIE W SAAS
                )
                db_session.add(new_absence)
            return jsonify({'success': True, 'message': 'Dodano nieobecność'})
        except Exception as e:
            return jsonify({'error': str(e)}), 500


@app.delete('/api/drivers/absences/<int:absence_id>')
@login_required
def delete_driver_absence(absence_id):
    """Usuwanie nieobecności KIEROWCY z weryfikacją dostępu do firmy"""
    current_firma_id = session.get('firma_id', 1)
    
    try:
        with session_scope() as db_session:
            # Szukamy w tabeli DriverAbsence z filtrem firma_id
            absence = db_session.query(DriverAbsence).filter_by(
                id=absence_id,
                firma_id=current_firma_id  # <--- TEN FILTR!
            ).first()

            if not absence:
                return jsonify({'error': 'Nieobecność nie znaleziona lub brak dostępu'}), 404

            # Pobieramy dane do loga przed usunięciem
            driver_id = absence.driver_id
            reason = absence.reason

            db_session.delete(absence)

            # Logujemy akcję
            log_activity("USUNIECIE_L4_KIEROWCY",
                         f"Usunięto nieobecność ID {absence_id} (Kierowca ID: {driver_id}, powód: {reason})")

        return jsonify({'success': True, 'message': 'Usunięto pomyślnie'})

    except Exception as e:
        print(f"Błąd usuwania L4 kierowcy: {e}")
        return jsonify({'error': str(e)}), 500


# ==========================================
# === GENEROWANIE LINKU "BEZ KLIENTA" (TWORZY NOWEGO) ===
# ==========================================

@app.route('/api/journal/generate-new', methods=['POST'])
@login_required
def generate_new_journal_link():
    """Tworzy anonimowego użytkownika dzienniczka i zwraca link."""
    try:
        with session_scope() as db_session:
            import uuid

            # 1. Generujemy token
            new_token = str(uuid.uuid4())

            # 2. Tworzymy użytkownika w nowej tabeli
            new_user = DiaryUser(public_token=new_token)

            db_session.add(new_user)
            db_session.flush()

            # 3. Generujemy link
            # Zwróć uwagę, że używamy tej samej trasy 'external_journal' co wcześniej
            full_link = url_for('external_journal', client_uuid=new_token, _external=True)

            return jsonify({
                'link': full_link,
                'message': 'Utworzono nowy, anonimowy dziennik.'
            })

    except Exception as e:
        print(f"Błąd generowania dziennika: {e}")
        return jsonify({'error': str(e)}), 500


'''@app.delete('/api/absences/<int:absence_id>')
@admin_required
def delete_absence(absence_id):
    try:
        with session_scope() as db_session:
            db_session.query(DriverAbsence).filter_by(id=absence_id).delete()
        return jsonify({'success': True})
    except Exception as e:
        return jsonify({'error': str(e)}), 500'''


# --- RAPORTY / OPINIE KLIENTA ---

@app.route('/api/clients/<int:client_id>/reports', methods=['GET'])
def get_client_reports(client_id):
    """Pobiera listę zapisanych opinii dla klienta."""
    with session_scope() as session:
        reports = session.query(ClientReport).filter(
            ClientReport.client_id == client_id
        ).order_by(ClientReport.created_at.desc()).all()

        return jsonify([{
            'id': r.id,
            'content': r.content,
            'period': r.period,
            'created_at': r.created_at.strftime('%Y-%m-%d %H:%M')
        } for r in reports])

@app.route('/api/clients/merge', methods=['POST'])
@login_required
def merge_clients_api():
    """
    Scala dwa konta klientów w jedno.
    Przenosi wszystkie relacje z duplicate_id na primary_id, a następnie usuwa duplicate_id.
    """
    # Zabezpieczenie - tylko admin może scalać
    if not current_user.is_admin:
        return jsonify({"error": "Tylko administrator może scalać klientów."}), 403
        
    data = request.get_json()
    primary_id = data.get('primary_id')
    duplicate_id = data.get('duplicate_id')
    
    if not primary_id or not duplicate_id or primary_id == duplicate_id:
        return jsonify({"error": "Brak poprawnego ID głównego i duplikatu."}), 400
        
    try:
        with engine.begin() as conn:
            # 1. Przepinamy proste tabele bezpośrednie (tam gdzie nie ma ryzyka duplikatu po scaleniu)
            tables = [
                "schedule_slots", "client_notes", "paid_records", 
                "client_documents", "client_unavailability", "dziennik", 
                "client_reports", "event_groups", "tus_member_bonuses", 
                "tus_general_bonuses"
            ]
            for table in tables:
                conn.execute(text(f"UPDATE {table} SET client_id = :pid WHERE client_id = :did"), 
                             {"pid": primary_id, "did": duplicate_id})
            
            # 2. Przepinamy tabele TUS (ostrożnie, bo mają Unique Constraints)
            # Jeśli primary_id i duplicate_id obaj figurują w danej grupie/sesji, to duplikat zostaje po prostu skasowany
            
            # A) Członkostwo w grupie TUS
            conn.execute(text("""
                UPDATE tus_group_members SET client_id = :pid 
                WHERE client_id = :did AND group_id NOT IN (SELECT group_id FROM tus_group_members WHERE client_id = :pid)
            """), {"pid": primary_id, "did": duplicate_id})
            conn.execute(text("DELETE FROM tus_group_members WHERE client_id = :did"), {"did": duplicate_id})
            
            # B) Obecność na sesji TUS
            conn.execute(text("""
                UPDATE tus_session_attendance SET client_id = :pid 
                WHERE client_id = :did AND session_id NOT IN (SELECT session_id FROM tus_session_attendance WHERE client_id = :pid)
            """), {"pid": primary_id, "did": duplicate_id})
            conn.execute(text("DELETE FROM tus_session_attendance WHERE client_id = :did"), {"did": duplicate_id})

            # C) Wyniki punktowe (scores) - sprawdza relację: sesja + zachowanie
            conn.execute(text("""
                UPDATE tus_session_member_scores SET client_id = :pid 
                WHERE client_id = :did AND (session_id, behavior_id) NOT IN (SELECT session_id, behavior_id FROM tus_session_member_scores WHERE client_id = :pid)
            """), {"pid": primary_id, "did": duplicate_id})
            conn.execute(text("DELETE FROM tus_session_member_scores WHERE client_id = :did"), {"did": duplicate_id})

            # D) Częściowe nagrody
            conn.execute(text("""
                UPDATE tus_session_partial_rewards SET client_id = :pid 
                WHERE client_id = :did AND session_id NOT IN (SELECT session_id FROM tus_session_partial_rewards WHERE client_id = :pid)
            """), {"pid": primary_id, "did": duplicate_id})
            conn.execute(text("DELETE FROM tus_session_partial_rewards WHERE client_id = :did"), {"did": duplicate_id})

            # 3. Usuwamy zdublowane, puste konto
            conn.execute(text("DELETE FROM clients WHERE id = :did"), {"did": duplicate_id})
            
        # Logujemy akcję w systemie
        log_activity("SCALENIE_KLIENTOW", f"Przeniesiono historię z ID {duplicate_id} na konto ID {primary_id} i usunięto duplikat.")
        return jsonify({"success": True, "message": "Konta zostały poprawnie scalone!"}), 200
        
    except Exception as e:
        print(f"Błąd scalania klientów: {e}")
        import traceback
        traceback.print_exc()
        return jsonify({"error": str(e)}), 500


@app.route('/api/clients/<int:client_id>/reports', methods=['POST'])
def save_client_report(client_id):
    """Zapisuje wygenerowaną opinię."""
    data = request.get_json()
    content = data.get('content')
    period = data.get('period')

    if not content:
        return jsonify({'error': 'Treść jest pusta'}), 400

    with session_scope() as session:
        new_report = ClientReport(
            client_id=client_id,
            content=content,
            period=period
        )
        session.add(new_report)
        # Commit następuje automatycznie przy wyjściu z session_scope

    return jsonify({'message': 'Zapisano opinię'}), 201


@app.route('/api/reports/<int:report_id>', methods=['DELETE'])
def delete_client_report(report_id):
    """Usuwa zapisaną opinię."""
    with session_scope() as session:
        session.query(ClientReport).filter(ClientReport.id == report_id).delete()
    return jsonify({'message': 'Usunięto'}), 200


@app.route('/api/ai/predict-client-limit', methods=['GET'])
@login_required
def predict_client_limit_fallback():
    """
    Endpoint obsługujący zapytania analityczne bota z panel.js.
    Zwraca bezpieczną wartość domyślną zapobiegając błędom 404 w konsoli przeglądarki.
    """
    client_id = request.args.get('client_id', type=int)
    month = request.args.get('month', '')
    current_firma_id = session.get('firma_id', 1)

    if not client_id:
        return jsonify({"error": "Brak parametru client_id"}), 400

    try:
        with engine.connect() as conn:
            # Weryfikacja lokatora (SaaS Tenant Lock)
            client_exists = conn.execute(
                text("SELECT 1 FROM clients WHERE id = :cid AND firma_id = :fid"),
                {"cid": client_id, "fid": current_firma_id}
            ).scalar()

            if not client_exists:
                return jsonify({"error": "Brak uprawnień lub pacjent nie istnieje"}), 403

        # Zwracamy standardowy bazowy przydział (8h), satysfakcjonując pętlę JavaScriptu
        return jsonify({
            "suggested_hours": 8.0,
            "rationale": "Standardowy miesięczny wymiar opieki SUO z decyzji administracyjnej."
        }), 200

    except Exception as e:
        return jsonify({"error": str(e)}), 500

#===============================================
#=== debugwanie sesji
#==============================================
@app.route('/api/debug/session', methods=['GET'])
@login_required
def debug_session():
    """Sprawdza zawartość sesji"""
    return jsonify({
        'firma_id': session.get('firma_id'),
        'user_id': session.get('user_id'),
        'username': session.get('username'),
        'is_admin': session.get('is_admin'),
        'session_keys': list(session.keys())
    }), 200
# =========================================================================
# === 🧭 ASYSTENT NAWIGACJI (CHATBOT PRZEWODNIK) ===
# =========================================================================
@app.route('/api/v1/site-guide', methods=['POST'])
def site_guide_chat():
    data = request.get_json()
    user_question = data.get('message', '')
    current_path = data.get('current_path', '/')  # Frontend prześle nam adres strony

    if not user_question:
        return jsonify({"reply": "Słucham? W czym mogę pomóc?"})

    # 1. MAPA OPISÓW STRON (Narracja)
    # AI sprawdzi ten słownik, żeby wiedzieć, o czym opowiadać
    context_map = {
        "/klient_panel": "Użytkownik jest na **Panelu Głównym (Pulpicie)**. To centrum sterowania. Widzi kafelki: Klienci, Harmonogram, Moduł TUS, Kierowcy. Są tu też przyciski 'Szybkie akcje' do dodawania pakietów.",
        "/klient_panel/clients": "Użytkownik jest w **Bazie Klientów**. Widzi listę wszystkich beneficjentów. Może tu wyszukiwać, filtrować, dodawać nowych klientów oraz edytować ich dane.",
        "/klient_panel/client_panel": "Użytkownik jest w **Harmonogramie**. To główny kalendarz wizyt. Może tu planować zajęcia indywidualne, sprawdzać kolizje i zarządzać czasem terapeutów.",
        "/tus": "Użytkownik jest w **Module TUS**. Służy do zarządzania grupami Treningu Umiejętności Społecznych, sesjami i systemem punktowym.",
        "/driver-schedule-page": "Użytkownik jest w **Module Kierowcy**. Widzi tu plany transportowe (kto, kogo, skąd i dokąd wiezie).",
        "/manager": "Użytkownik jest w **Panelu Menadżera**. To miejsce do zarządzania dokumentacją, sprawozdaniami i projektami unijnymi.",
        "/poczekalnia": "Użytkownik jest w **Poczekalni**. To lista osób oczekujących na przyjęcie do fundacji.",
        "/terapeuta-panel": "Użytkownik jest w **Panelu Terapeuty**. Widok dedykowany dla specjalistów (mój grafik, moi pacjenci)."
    }

    # Pobieramy opis aktualnej strony (lub domyślny)
    current_context_desc = context_map.get(current_path, "Użytkownik jest na jednej z podstron systemu.")

    # 2. Instrukcja dla modelu
    system_instruction = f"""
    Jesteś Inteligentnym Narratorem i Przewodnikiem po systemie Fundacji.

    KONTEKST: {current_context_desc}

    ZASADY:
    1. Jeśli użytkownik pyta "Co to za strona?" lub "Co mogę tu zrobić?", opisz funkcje AKTUALNEJ strony bazując na Kontekście powyżej.
    2. Jeśli pyta o inną funkcję, wskaż mu drogę (np. "Aby dodać klienta, przejdź do zakładki Klienci").
    3. Odpowiadaj krótko, konkretnie i pomocnie.

    PYTANIE UŻYTKOWNIKA: "{user_question}"
    """

    try:
        api_key = os.getenv("GOOGLE_AI_API_KEY")
        if not api_key:
            return jsonify({"reply": "Błąd konfiguracji: Brak klucza API."})

        genai.configure(api_key=api_key)
        model = genai.GenerativeModel('gemini-3.5-flash')

        response = model.generate_content(
            system_instruction,
            generation_config={"temperature": 0.3, "max_output_tokens": 200}
        )

        return jsonify({"reply": response.text})

    except Exception as e:
        print(f"❌ Błąd Site Guide: {e}")
        return jsonify({"reply": "Przepraszam, mam chwilowy problem z połączeniem."})



# Wywołaj diagnostykę
debug_endpoints()

# === INICJALIZACJA DOMYŚLNEGO UŻYTKOWNIKA ===
print("\n" + "=" * 60)
print("INICJALIZACJA DOMYŚLNEGO UŻYTKOWNIKA")
print("=" * 60)
# create_default_user()
print("=" * 60 + "\n")

# ==============================================================================
# === MODUŁ KADRY: umowy pracownicze + plan urlopów (planowanie i wykonanie) ===
# ==============================================================================

kadry_bp = Blueprint('kadry', __name__, template_folder='templates')

UMOWY_UPLOAD_FOLDER = 'uploads/umowy'
os.makedirs(UMOWY_UPLOAD_FOLDER, exist_ok=True)
app.config['UMOWY_UPLOAD_FOLDER'] = UMOWY_UPLOAD_FOLDER

UMOWA_TYPY = ['umowa_o_prace', 'umowa_zlecenie', 'umowa_o_dzielo', 'B2B', 'staz', 'inne']
URLOP_TYPY = ['wypoczynkowy', 'na_zadanie', 'bezplatny', 'opiekuńczy', 'inny']
URLOP_STATUSY = ['oczekuje', 'zaakceptowany', 'odrzucony', 'anulowany']
ROCZNY_LIMIT_URLOPU = 26  # dni roboczych w roku


class Umowa(Base):
    """Umowa z pracownikiem (moduł kadry)."""
    __tablename__ = 'kadry_umowy'

    id = Column(Integer, primary_key=True)
    pracownik_id = Column(Integer, ForeignKey('users.id', ondelete='CASCADE'), nullable=False)
    typ = Column(String(50), nullable=False, default='umowa_o_prace')
    stanowisko = Column(String(255))
    wynagrodzenie = Column(Float)
    data_zawarcia = Column(Date, nullable=False)
    data_od = Column(Date)
    data_do = Column(Date)
    file_path = Column(String(500))
    file_name = Column(String(255))
    notes = Column(Text)
    created_at = Column(DateTime(timezone=True), server_default=func.now())
    firma_id = Column(Integer, ForeignKey('firma.id', ondelete='CASCADE'), nullable=False)

    pracownik = relationship('User', foreign_keys=[pracownik_id])

    def as_dict(self):
        return {
            'id': self.id,
            'pracownik_id': self.pracownik_id,
            'pracownik': self.pracownik.full_name if self.pracownik else None,
            'typ': self.typ,
            'stanowisko': self.stanowisko,
            'wynagrodzenie': self.wynagrodzenie,
            'data_zawarcia': self.data_zawarcia.isoformat() if self.data_zawarcia else None,
            'data_od': self.data_od.isoformat() if self.data_od else None,
            'data_do': self.data_do.isoformat() if self.data_do else None,
            'file_name': self.file_name,
            'has_file': bool(self.file_path),
            'notes': self.notes,
            'created_at': self.created_at.isoformat() if self.created_at else None,
        }


class WniosekUrlopowy(Base):
    """Wniosek / plan urlopu pracownika z oznaczeniem wykonania planu."""
    __tablename__ = 'kadry_urlopy'

    id = Column(Integer, primary_key=True)
    pracownik_id = Column(Integer, ForeignKey('users.id', ondelete='CASCADE'), nullable=False)
    typ = Column(String(50), default='wypoczynkowy')
    data_od = Column(Date, nullable=False)
    data_do = Column(Date, nullable=False)
    liczba_dni = Column(Integer, nullable=False, default=1)
    planowany = Column(Boolean, default=False)   # wpis w PLANIE urlopów
    wykonany = Column(Boolean, default=False)    # wykonanie planu (faktycznie wykorzystany)
    status = Column(String(20), default='oczekuje')
    komentarz = Column(Text)
    zatwierdzil_id = Column(Integer, ForeignKey('users.id'))
    created_at = Column(DateTime(timezone=True), server_default=func.now())
    firma_id = Column(Integer, ForeignKey('firma.id', ondelete='CASCADE'), nullable=False)

    pracownik = relationship('User', foreign_keys=[pracownik_id])
    zatwierdzil = relationship('User', foreign_keys=[zatwierdzil_id])

    def as_dict(self):
        return {
            'id': self.id,
            'pracownik_id': self.pracownik_id,
            'pracownik': self.pracownik.full_name if self.pracownik else None,
            'typ': self.typ,
            'data_od': self.data_od.isoformat() if self.data_od else None,
            'data_do': self.data_do.isoformat() if self.data_do else None,
            'liczba_dni': self.liczba_dni,
            'planowany': bool(self.planowany),
            'wykonany': bool(self.wykonany),
            'status': self.status,
            'komentarz': self.komentarz,
            'zatwierdzil': self.zatwierdzil.full_name if self.zatwierdzil else None,
            'created_at': self.created_at.isoformat() if self.created_at else None,
        }


def kadry_required(view):
    """Dekorator: admin, sekretariat lub uprawnienie 'kadry'."""
    @functools.wraps(view)
    @login_required
    def wrapped(**kwargs):
        with session_scope() as db_session:
            user = db_session.get(User, current_user.id)
            if user and (user.is_admin or user.is_secretariat or user.has_permission('kadry')):
                return view(**kwargs)
        if request.path.startswith('/api/'):
            return jsonify(message="Brak uprawnień do modułu Kadry"), 403
        flash('Brak uprawnień do modułu Kadry.', 'danger')
        return redirect(url_for('main_index'))
    return wrapped


def _kadry_parse_date(value, field):
    if not value:
        raise ValueError(f'Brak daty: {field}')
    return datetime.fromisoformat(str(value)[:10]).date()


def _dni_robocze(data_od, data_do):
    """Liczba dni roboczych (Pn-Pt) w zakresie włącznie."""
    if not data_od or not data_do or data_do < data_od:
        return 0
    dni = 0
    d = data_od
    while d <= data_do:
        if d.weekday() < 5:
            dni += 1
        d += timedelta(days=1)
    return dni


# --- Strona modułu ---
@kadry_bp.route('/kadry')
@kadry_required
def kadry_page():
    """Strona główna modułu Kadry (umowy + plan urlopów)."""
    return render_template('kadry.html')


# --- Lista pracowników (do selectów w kadrach) ---
@kadry_bp.route('/api/kadry/pracownicy', methods=['GET'])
@kadry_required
def kadry_pracownicy():
    current_firma_id = session.get('firma_id', 1)
    with session_scope() as db_session:
        users = db_session.query(User).filter(
            User.firma_id == current_firma_id
        ).order_by(User.full_name).all()
        return jsonify([{
            'id': u.id,
            'full_name': u.full_name,
            'username': u.username,
            'is_admin': u.is_admin,
            'therapist_id': u.therapist_id,
            'driver_id': u.driver_id,
        } for u in users]), 200


# ============================ UMOWY (CRUD + plik) ============================

@kadry_bp.route('/api/kadry/umowy', methods=['GET'])
@kadry_required
def kadry_umowy_lista():
    current_firma_id = session.get('firma_id', 1)
    pracownik_id = request.args.get('pracownik_id', type=int)
    with session_scope() as db_session:
        q = db_session.query(Umowa).filter(Umowa.firma_id == current_firma_id)
        if pracownik_id:
            q = q.filter(Umowa.pracownik_id == pracownik_id)
        umowy = q.order_by(Umowa.data_zawarcia.desc(), Umowa.id.desc()).all()
        return jsonify([u.as_dict() for u in umowy]), 200


@kadry_bp.route('/api/kadry/umowy', methods=['POST'])
@kadry_required
def kadry_umowa_dodaj():
    """Tworzy umowę (multipart/form-data; opcjonalny plik PDF/skan/doc)."""
    current_firma_id = session.get('firma_id', 1)
    form = request.form
    try:
        pracownik_id = int(form.get('pracownik_id'))
        data_zawarcia = _kadry_parse_date(form.get('data_zawarcia'), 'data_zawarcia')
    except (ValueError, TypeError) as e:
        return jsonify({'error': str(e)}), 400

    typ = form.get('typ', 'umowa_o_prace')
    if typ not in UMOWA_TYPY:
        return jsonify({'error': f'Nieprawidłowy typ umowy. Dozwolone: {UMOWA_TYPY}'}), 400

    file_path = file_name = None
    file = request.files.get('plik')
    if file and file.filename:
        if not allowed_file(file.filename):
            return jsonify({'error': 'Niedozwolony format pliku (dozwolone: pdf, jpg, png, doc, docx)'}), 400
        file_name = secure_filename(file.filename)
        unique_name = f"{uuid.uuid4()}_{file_name}"
        file_path = os.path.join(app.config['UMOWY_UPLOAD_FOLDER'], unique_name)
        file.save(file_path)

    try:
        with session_scope() as db_session:
            pracownik = db_session.query(User).filter(
                User.id == pracownik_id, User.firma_id == current_firma_id
            ).first()
            if not pracownik:
                return jsonify({'error': 'Pracownik nie należy do tej firmy'}), 404

            data_od = _kadry_parse_date(form.get('data_od'), 'data_od') if form.get('data_od') else None
            data_do = _kadry_parse_date(form.get('data_do'), 'data_do') if form.get('data_do') else None
            if data_od and data_do and data_do < data_od:
                return jsonify({'error': 'data_do nie może być wcześniejsza niż data_od'}), 400

            umowa = Umowa(
                pracownik_id=pracownik_id,
                typ=typ,
                stanowisko=(form.get('stanowisko') or '').strip() or None,
                wynagrodzenie=float(form['wynagrodzenie']) if form.get('wynagrodzenie') else None,
                data_zawarcia=data_zawarcia,
                data_od=data_od,
                data_do=data_do,
                file_path=file_path,
                file_name=file_name,
                notes=(form.get('notes') or '').strip() or None,
                firma_id=current_firma_id,
            )
            db_session.add(umowa)
            db_session.flush()
            result = umowa.as_dict()
        log_activity('KADRY_DODANIE_UMOWY', f'Umowa ID {result["id"]} dla: {result["pracownik"]} ({typ})')
        return jsonify(result), 201
    except Exception as e:
        if file_path and os.path.exists(file_path):
            try:
                os.remove(file_path)
            except OSError:
                pass
        print(f'Błąd dodawania umowy: {e}')
        traceback.print_exc()
        return jsonify({'error': str(e)}), 500


@kadry_bp.route('/api/kadry/umowy/<int:umowa_id>', methods=['GET'])
@kadry_required
def kadry_umowa_szczegoly(umowa_id):
    current_firma_id = session.get('firma_id', 1)
    with session_scope() as db_session:
        umowa = db_session.query(Umowa).filter(
            Umowa.id == umowa_id, Umowa.firma_id == current_firma_id
        ).first()
        if not umowa:
            return jsonify({'error': 'Umowa nie znaleziona'}), 404
        return jsonify(umowa.as_dict()), 200


@kadry_bp.route('/api/kadry/umowy/<int:umowa_id>', methods=['PUT', 'PATCH'])
@kadry_required
def kadry_umowa_edytuj(umowa_id):
    """Aktualizuje umowę. Przyjmuje JSON lub multipart (z opcjonalnym nowym plikiem)."""
    current_firma_id = session.get('firma_id', 1)
    data = request.get_json(silent=True) or request.form
    if not data:
        return jsonify({'error': 'Brak danych'}), 400

    try:
        with session_scope() as db_session:
            umowa = db_session.query(Umowa).filter(
                Umowa.id == umowa_id, Umowa.firma_id == current_firma_id
            ).first()
            if not umowa:
                return jsonify({'error': 'Umowa nie znaleziona'}), 404

            if 'pracownik_id' in data and data.get('pracownik_id'):
                pid = int(data['pracownik_id'])
                if not db_session.query(User).filter(User.id == pid, User.firma_id == current_firma_id).first():
                    return jsonify({'error': 'Pracownik nie należy do tej firmy'}), 404
                umowa.pracownik_id = pid
            if 'typ' in data:
                if data['typ'] not in UMOWA_TYPY:
                    return jsonify({'error': f'Nieprawidłowy typ umowy. Dozwolone: {UMOWA_TYPY}'}), 400
                umowa.typ = data['typ']
            if 'stanowisko' in data:
                umowa.stanowisko = (data.get('stanowisko') or '').strip() or None
            if 'wynagrodzenie' in data:
                umowa.wynagrodzenie = float(data['wynagrodzenie']) if data.get('wynagrodzenie') else None
            if 'data_zawarcia' in data and data.get('data_zawarcia'):
                umowa.data_zawarcia = _kadry_parse_date(data['data_zawarcia'], 'data_zawarcia')
            if 'data_od' in data:
                umowa.data_od = _kadry_parse_date(data['data_od'], 'data_od') if data.get('data_od') else None
            if 'data_do' in data:
                umowa.data_do = _kadry_parse_date(data['data_do'], 'data_do') if data.get('data_do') else None
            if 'notes' in data:
                umowa.notes = (data.get('notes') or '').strip() or None
            if umowa.data_od and umowa.data_do and umowa.data_do < umowa.data_od:
                return jsonify({'error': 'data_do nie może być wcześniejsza niż data_od'}), 400

            # opcjonalna podmiana pliku
            file = request.files.get('plik')
            if file and file.filename:
                if not allowed_file(file.filename):
                    return jsonify({'error': 'Niedozwolony format pliku'}), 400
                if umowa.file_path and os.path.exists(umowa.file_path):
                    try:
                        os.remove(umowa.file_path)
                    except OSError:
                        pass
                umowa.file_name = secure_filename(file.filename)
                umowa.file_path = os.path.join(
                    app.config['UMOWY_UPLOAD_FOLDER'], f"{uuid.uuid4()}_{umowa.file_name}"
                )
                file.save(umowa.file_path)

            db_session.flush()
            result = umowa.as_dict()
        log_activity('KADRY_EDYCJA_UMOWY', f'Umowa ID {umowa_id} zaktualizowana')
        return jsonify(result), 200
    except ValueError as e:
        return jsonify({'error': str(e)}), 400
    except Exception as e:
        print(f'Błąd edycji umowy: {e}')
        traceback.print_exc()
        return jsonify({'error': str(e)}), 500


@kadry_bp.route('/api/kadry/umowy/<int:umowa_id>', methods=['DELETE'])
@kadry_required
def kadry_umowa_usun(umowa_id):
    current_firma_id = session.get('firma_id', 1)
    with session_scope() as db_session:
        umowa = db_session.query(Umowa).filter(
            Umowa.id == umowa_id, Umowa.firma_id == current_firma_id
        ).first()
        if not umowa:
            return jsonify({'error': 'Umowa nie znaleziona'}), 404
        file_path = umowa.file_path
        tytul = f'{umowa.typ} / {umowa.pracownik.full_name if umowa.pracownik else umowa.pracownik_id}'
        db_session.delete(umowa)
    if file_path and os.path.exists(file_path):
        try:
            os.remove(file_path)
        except OSError:
            pass
    log_activity('KADRY_USUNIECIE_UMOWY', f'Usunięto umowę ID {umowa_id} ({tytul})')
    return jsonify({'message': 'Umowa usunięta'}), 200


@kadry_bp.route('/api/kadry/umowy/<int:umowa_id>/plik', methods=['GET'])
@kadry_required
def kadry_umowa_plik(umowa_id):
    """Pobiera załączony plik umowy."""
    current_firma_id = session.get('firma_id', 1)
    with session_scope() as db_session:
        umowa = db_session.query(Umowa).filter(
            Umowa.id == umowa_id, Umowa.firma_id == current_firma_id
        ).first()
        if not umowa or not umowa.file_path:
            return jsonify({'error': 'Brak pliku dla tej umowy'}), 404
        path = umowa.file_path
        name = umowa.file_name or os.path.basename(path)
    if not os.path.exists(path):
        return jsonify({'error': 'Plik nie istnieje na serwerze'}), 404
    log_activity('KADRY_POBRANIE_PLIKU_UMOWY', f'Umowa ID {umowa_id}, plik: {name}')
    return send_file(path, as_attachment=True, download_name=name)


# ===================== PLAN URLOPÓW (plan + wykonanie) =====================

@kadry_bp.route('/api/kadry/urlopy', methods=['GET'])
@kadry_required
def kadry_urlopy_lista():
    """Lista wniosków/planu urlopów. Filtry: miesiac=YYYY-MM, rok=YYYY, status, pracownik_id, planowany=1."""
    current_firma_id = session.get('firma_id', 1)
    miesiac = request.args.get('miesiac')
    rok = request.args.get('rok', type=int)
    status = request.args.get('status')
    pracownik_id = request.args.get('pracownik_id', type=int)
    planowany = request.args.get('planowany')

    with session_scope() as db_session:
        q = db_session.query(WniosekUrlopowy).filter(WniosekUrlopowy.firma_id == current_firma_id)
        if miesiac:
            try:
                y, m = map(int, miesiac.split('-'))
                q = q.filter(extract('year', WniosekUrlopowy.data_od) == y,
                             extract('month', WniosekUrlopowy.data_od) == m)
            except ValueError:
                return jsonify({'error': 'Nieprawidłowy format miesiąca (YYYY-MM)'}), 400
        if rok:
            q = q.filter(extract('year', WniosekUrlopowy.data_od) == rok)
        if status:
            q = q.filter(WniosekUrlopowy.status == status)
        if pracownik_id:
            q = q.filter(WniosekUrlopowy.pracownik_id == pracownik_id)
        if planowany is not None:
            q = q.filter(WniosekUrlopowy.planowany == (planowany in ('1', 'true', 'True')))
        wnioski = q.order_by(WniosekUrlopowy.data_od).all()
        return jsonify([w.as_dict() for w in wnioski]), 200


@kadry_bp.route('/api/kadry/urlopy', methods=['POST'])
@kadry_required
def kadry_urlop_dodaj():
    """Dodaje wniosek urlopowy lub wpis do PLANU urlopów (planowany=true)."""
    current_firma_id = session.get('firma_id', 1)
    data = request.get_json(silent=True) or {}
    try:
        pracownik_id = int(data.get('pracownik_id'))
        data_od = _kadry_parse_date(data.get('data_od'), 'data_od')
        data_do = _kadry_parse_date(data.get('data_do'), 'data_do')
    except (ValueError, TypeError) as e:
        return jsonify({'error': str(e)}), 400
    if data_do < data_od:
        return jsonify({'error': 'data_do nie może być wcześniejsza niż data_od'}), 400

    typ = data.get('typ', 'wypoczynkowy')
    if typ not in URLOP_TYPY:
        return jsonify({'error': f'Nieprawidłowy typ urlopu. Dozwolone: {URLOP_TYPY}'}), 400

    with session_scope() as db_session:
        pracownik = db_session.query(User).filter(
            User.id == pracownik_id, User.firma_id == current_firma_id
        ).first()
        if not pracownik:
            return jsonify({'error': 'Pracownik nie należy do tej firmy'}), 404

        wniosek = WniosekUrlopowy(
            pracownik_id=pracownik_id,
            typ=typ,
            data_od=data_od,
            data_do=data_do,
            liczba_dni=int(data.get('liczba_dni') or _dni_robocze(data_od, data_do)),
            planowany=bool(data.get('planowany', False)),
            wykonany=False,
            status='oczekuje',
            komentarz=(data.get('komentarz') or '').strip() or None,
            firma_id=current_firma_id,
        )
        db_session.add(wniosek)
        db_session.flush()
        result = wniosek.as_dict()
    log_activity('KADRY_DODANIE_URLOPU',
                 f'{"Plan" if result["planowany"] else "Wniosek"} urlopu ID {result["id"]}: '
                 f'{result["pracownik"]} {result["data_od"]}..{result["data_do"]} ({result["liczba_dni"]} dni)')
    return jsonify(result), 201


@kadry_bp.route('/api/kadry/urlopy/<int:urlop_id>', methods=['PUT', 'PATCH'])
@kadry_required
def kadry_urlop_edytuj(urlop_id):
    current_firma_id = session.get('firma_id', 1)
    data = request.get_json(silent=True) or {}
    if not data:
        return jsonify({'error': 'Brak danych'}), 400
    try:
        with session_scope() as db_session:
            w = db_session.query(WniosekUrlopowy).filter(
                WniosekUrlopowy.id == urlop_id, WniosekUrlopowy.firma_id == current_firma_id
            ).first()
            if not w:
                return jsonify({'error': 'Wpis urlopowy nie znaleziony'}), 404

            if 'pracownik_id' in data and data.get('pracownik_id'):
                pid = int(data['pracownik_id'])
                if not db_session.query(User).filter(User.id == pid, User.firma_id == current_firma_id).first():
                    return jsonify({'error': 'Pracownik nie należy do tej firmy'}), 404
                w.pracownik_id = pid
            if 'typ' in data:
                if data['typ'] not in URLOP_TYPY:
                    return jsonify({'error': f'Nieprawidłowy typ urlopu. Dozwolone: {URLOP_TYPY}'}), 400
                w.typ = data['typ']
            if 'data_od' in data and data.get('data_od'):
                w.data_od = _kadry_parse_date(data['data_od'], 'data_od')
            if 'data_do' in data and data.get('data_do'):
                w.data_do = _kadry_parse_date(data['data_do'], 'data_do')
            if w.data_do < w.data_od:
                return jsonify({'error': 'data_do nie może być wcześniejsza niż data_od'}), 400
            if 'liczba_dni' in data and data.get('liczba_dni'):
                w.liczba_dni = int(data['liczba_dni'])
            elif 'data_od' in data or 'data_do' in data:
                w.liczba_dni = _dni_robocze(w.data_od, w.data_do)
            if 'planowany' in data:
                w.planowany = bool(data.get('planowany'))
            if 'wykonany' in data:
                w.wykonany = bool(data.get('wykonany'))
            if 'komentarz' in data:
                w.komentarz = (data.get('komentarz') or '').strip() or None

            db_session.flush()
            result = w.as_dict()
        log_activity('KADRY_EDYCJA_URLOPU', f'Wpis urlopowy ID {urlop_id} zaktualizowany')
        return jsonify(result), 200
    except ValueError as e:
        return jsonify({'error': str(e)}), 400
    except Exception as e:
        print(f'Błąd edycji urlopu: {e}')
        traceback.print_exc()
        return jsonify({'error': str(e)}), 500


@kadry_bp.route('/api/kadry/urlopy/<int:urlop_id>', methods=['DELETE'])
@kadry_required
def kadry_urlop_usun(urlop_id):
    current_firma_id = session.get('firma_id', 1)
    with session_scope() as db_session:
        w = db_session.query(WniosekUrlopowy).filter(
            WniosekUrlopowy.id == urlop_id, WniosekUrlopowy.firma_id == current_firma_id
        ).first()
        if not w:
            return jsonify({'error': 'Wpis urlopowy nie znaleziony'}), 404
        opis = f'{w.pracownik.full_name if w.pracownik else w.pracownik_id} {w.data_od}..{w.data_do}'
        db_session.delete(w)
    log_activity('KADRY_USUNIECIE_URLOPU', f'Usunięto wpis ID {urlop_id} ({opis})')
    return jsonify({'message': 'Wpis usunięty'}), 200


@kadry_bp.route('/api/kadry/urlopy/<int:urlop_id>/status', methods=['POST'])
@kadry_required
def kadry_urlop_status(urlop_id):
    """Akceptacja / odrzucenie / anulowanie wniosku (wymaga admina lub uprawnienia kadry)."""
    current_firma_id = session.get('firma_id', 1)
    data = request.get_json(silent=True) or {}
    nowy_status = data.get('status')
    if nowy_status not in URLOP_STATUSY:
        return jsonify({'error': f'Nieprawidłowy status. Dozwolone: {URLOP_STATUSY}'}), 400

    with session_scope() as db_session:
        w = db_session.query(WniosekUrlopowy).filter(
            WniosekUrlopowy.id == urlop_id, WniosekUrlopowy.firma_id == current_firma_id
        ).first()
        if not w:
            return jsonify({'error': 'Wpis urlopowy nie znaleziony'}), 404
        w.status = nowy_status
        if nowy_status in ('zaakceptowany', 'odrzucony'):
            w.zatwierdzil_id = current_user.id
        db_session.flush()
        result = w.as_dict()
    log_activity('KADRY_STATUS_URLOPU',
                 f'Wpis ID {urlop_id} ({result["pracownik"]}) -> status: {nowy_status}')
    return jsonify(result), 200


@kadry_bp.route('/api/kadry/urlopy/<int:urlop_id>/wykonaj', methods=['POST'])
@kadry_required
def kadry_urlop_wykonaj(urlop_id):
    """Oznacza planowany urlop jako WYKONANY (wykonanie planu - faktyczne wykorzystanie dni)."""
    current_firma_id = session.get('firma_id', 1)
    with session_scope() as db_session:
        w = db_session.query(WniosekUrlopowy).filter(
            WniosekUrlopowy.id == urlop_id, WniosekUrlopowy.firma_id == current_firma_id
        ).first()
        if not w:
            return jsonify({'error': 'Wpis urlopowy nie znaleziony'}), 404
        w.wykonany = True
        db_session.flush()
        result = w.as_dict()
    log_activity('KADRY_WYKONANIE_URLOPU',
                 f'Wpis ID {urlop_id} ({result["pracownik"]}) oznaczony jako wykonany: '
                 f'{result["liczba_dni"]} dni')
    return jsonify(result), 200


@kadry_bp.route('/api/kadry/urlopy/rozliczenie', methods=['GET'])
@kadry_required
def kadry_urlopy_rozliczenie():
    """Rozliczenie planu vs wykonanie: per pracownik i rok - dni zaplanowane, wykonane, pozostałe z limitu."""
    current_firma_id = session.get('firma_id', 1)
    rok = request.args.get('rok', type=int) or datetime.now(TZ).year

    with session_scope() as db_session:
        users = db_session.query(User).filter(User.firma_id == current_firma_id).order_by(User.full_name).all()
        wnioski = db_session.query(WniosekUrlopowy).filter(
            WniosekUrlopowy.firma_id == current_firma_id,
            extract('year', WniosekUrlopowy.data_od) == rok,
            WniosekUrlopowy.typ == 'wypoczynkowy',
            WniosekUrlopowy.status.in_(('oczekuje', 'zaakceptowany')),
        ).all()

        per_user = {u.id: {'zaplanowane': 0, 'wykonane': 0} for u in users}
        for w in wnioski:
            if w.pracownik_id not in per_user:
                continue
            if w.wykonany:
                per_user[w.pracownik_id]['wykonane'] += w.liczba_dni
            elif w.planowany:
                per_user[w.pracownik_id]['zaplanowane'] += w.liczba_dni

        wynik = [{
            'pracownik_id': u.id,
            'pracownik': u.full_name,
            'rok': rok,
            'limit_dni': ROCZNY_LIMIT_URLOPU,
            'dni_zaplanowane': per_user[u.id]['zaplanowane'],
            'dni_wykonane': per_user[u.id]['wykonane'],
            'dni_pozostale': max(0, ROCZNY_LIMIT_URLOPU - per_user[u.id]['wykonane']),
        } for u in users]
        return jsonify({'rok': rok, 'limit_dni': ROCZNY_LIMIT_URLOPU, 'rozliczenie': wynik}), 200


# ==============================================================================
# === WYBÓR WIDOCZNYCH MODUŁÓW PRZEZ UŻYTKOWNIKA (pozostałe ukryte w menu) ===
# ==============================================================================

# Rejestr wszystkich modułów. "key" = data-module-id kafelka na dashboardzie
# (zgodne z katalogiem ALL_SYSTEM_PAGES w dashboard.html); "perms" = aliasy kluczy
# uprawnień (permissions), które otwierają dany moduł — dzięki temu wybór
# użytkownika łączy się z RBAC.
ALL_MODULES = [
    # --- Główne moduły (kafelki na pulpicie) ---
    {"key": "clients",       "label": "Klienci",               "url": "/klient_panel",                    "perms": ["clients", "client_panel"]},
    {"key": "suo",           "label": "Panel SUO",             "url": "/klient_panel/panel",              "perms": ["suo"]},
    {"key": "calendar",      "label": "Grafik Wizyt",          "url": "/klient_panel/client_panel_grafik", "perms": ["calendar", "grafik", "client_panel_grafik"]},
    {"key": "drivers",       "label": "Kierowcy (Logistyka)",  "url": "/driver-schedule-page",            "perms": ["drivers"]},
    {"key": "tus",           "label": "Grupy TUS",             "url": "/tus",                             "perms": ["tus"]},
    {"key": "planer_masowy", "label": "Planer Masowy AI",      "url": "/manager/planer-masowy",           "perms": ["planer_masowy"]},
    {"key": "manager",       "label": "Manager (Główny)",      "url": "/manager",                         "perms": ["manager"]},
    {"key": "therapist",     "label": "Mój Panel Terapeuty",   "url": "/terapeuta-panel",                 "perms": ["therapist"]},
    # --- Dziennik & obsługa pacjentów ---
    {"key": "poczekalnia",       "label": "Poczekalnia",            "url": "/poczekalnia",                      "perms": ["poczekalnia"]},
    {"key": "dziennik",          "label": "Dziennik zajęć",         "url": "/klient_panel/dziennik",            "perms": ["dziennik"]},
    {"key": "lista_zestawienie", "label": "Zestawienie dziennika",  "url": "/klient_panel/lista_zestawienie",  "perms": ["lista_zestawienie", "lista"]},
    {"key": "historia",          "label": "Historia pacjentów",     "url": "/klient_panel/historia",            "perms": ["historia"]},
    {"key": "notes",             "label": "Notatki pacjentów",      "url": "/klient_panel/notes",               "perms": ["notes"]},
    {"key": "attendance",        "label": "Obecność indywidualna",  "url": "/klient_panel/indywidual-attendance", "perms": ["indywidual_attendance"]},
    # --- Manager, dokumenty & finanse ---
    {"key": "admission",     "label": "Karta przyjęcia",        "url": "/manager/admission",          "perms": []},
    {"key": "planer_ind",    "label": "Planer indywidualny",    "url": "/manager/planer-indywidualny", "perms": []},
    {"key": "plany_lista",   "label": "Plany terapeutyczne",    "url": "/manager/plany-lista",        "perms": []},
    {"key": "ipet",          "label": "Dokumenty IPET",         "url": "/manager/ipet",               "perms": ["ipet"]},
    {"key": "finanse",       "label": "Finanse & wpłaty",       "url": "/manager/finanse",            "perms": ["finance"]},
    {"key": "sprawozdania",  "label": "Sprawozdania okresowe",  "url": "/manager/sprawozdania",       "perms": []},
    {"key": "uchwaly",       "label": "Uchwały zarządu",        "url": "/manager/uchwaly",            "perms": ["resolutions"]},
    {"key": "projects",      "label": "Projekty",               "url": "/manager/projects",           "perms": []},
    {"key": "diagnozy",      "label": "Baza diagnoz",           "url": "/manager/diagnoza_list",      "perms": []},
    {"key": "diva5",         "label": "Raporty DIVA-5",         "url": "/manager/diva5-raporty",      "perms": []},
    {"key": "kadry",         "label": "Kadry",                  "url": "/manager/kadry",              "perms": ["kadry"]},
    {"key": "manage_users",  "label": "Użytkownicy i role",     "url": "/admin/manage-users",         "perms": ["manage_users"]},
]

# Moduły, których trasy są zabezpieczone tylko logowaniem (bez osobnego uprawnienia RBAC)
OPEN_MODULE_KEYS = {"tus", "admission", "planer_ind", "plany_lista", "sprawozdania", "projects", "diagnozy", "diva5", "manager"}


@app.route('/api/auth/modules', methods=['GET'])
@login_required
def get_my_visible_modules():
    """Zwraca wszystkie moduły, moduły dozwolone dla użytkownika oraz aktualnie widoczne (wybrane)."""
    return jsonify({
        'all': ALL_MODULES,
        'allowed': current_user.allowed_module_keys(),
        'visible': current_user.get_visible_modules(),
        'saved': current_user.visible_modules or ''
    }), 200


@app.route('/api/auth/modules', methods=['POST', 'PUT'])
@login_required
def save_my_visible_modules():
    """
    Zapisuje wybór modułów widocznych w menu — pozostałe zostają ukryte.
    Pusta lista (lub jej brak) = reset do domyślnej wartości (wszystkie widoczne).
    """
    data = request.get_json(silent=True) or {}
    modules = data.get('modules', [])

    if modules is None:
        modules = []
    if not isinstance(modules, list):
        return jsonify({'error': "Pole 'modules' musi być listą kluczy modułów (np. ['dziennik','grafik'])."}), 400

    modules = [str(m).strip() for m in modules if str(m).strip()]
    known = {m['key'] for m in ALL_MODULES}
    unknown = [m for m in modules if m not in known]
    if unknown:
        return jsonify({'error': f"Nieznane moduły: {', '.join(unknown)}",
                        'allowed_keys': sorted(known)}), 400

    # Admin może wybrać dowolne moduły; zwykły użytkownik tylko te, do których ma prawo
    rejected = []
    if not current_user.is_admin:
        allowed = set(current_user.allowed_module_keys())
        rejected = [m for m in modules if m not in allowed]
        modules = [m for m in modules if m in allowed]

    value = ','.join(modules)  # pusty string = wszystkie widoczne (domyślnie)

    try:
        with session_scope() as db_session:
            user = db_session.get(User, current_user.id)
            if not user:
                return jsonify({'error': 'Użytkownik nie istnieje.'}), 404
            user.visible_modules = value

        keys = [m['key'] for m in ALL_MODULES]
        visible = keys if not value else [k for k in keys if k in modules]

        log_activity(
            "ZMIANA_WIDOCZNYCH_MODUŁOW",
            f"Użytkownik '{current_user.username}' wybrał moduły: {value or '(wszystkie widoczne)'}"
            + (f"; odrzucono (brak uprawnień): {', '.join(rejected)}" if rejected else "")
        )
        return jsonify({'success': True, 'visible': visible, 'rejected': rejected}), 200

    except Exception as e:
        print(f"Błąd zapisu widocznych modułów: {e}")
        traceback.print_exc()
        return jsonify({'error': f'Wystąpił błąd serwera: {str(e)}'}), 500


@app.context_processor
def inject_visible_modules():
    """Wstrzykuje visible_modules / all_modules do każdego szablonu Jinja (menu można ukrywać)."""
    visible = [m['key'] for m in ALL_MODULES]
    try:
        if current_user and current_user.is_authenticated:
            visible = current_user.get_visible_modules()
    except Exception:
        pass
    return {'visible_modules': visible, 'all_modules': ALL_MODULES}


# ==============================================================================
# === PRZYPOMNIENIA DLA TERAPEUTÓW: WPISY W DZIENNIKU ZAJĘĆ ===
# ==============================================================================

def _can_manage_journal_reminders():
    """Admin, sekretariat lub osoba z uprawnieniem 'dziennik'."""
    if not (current_user and current_user.is_authenticated):
        return False
    return bool(
        current_user.is_admin
        or current_user.is_secretariat
        or current_user.has_permission('dziennik')
    )


def _parse_days(value, default=7):
    try:
        d = int(value)
    except (TypeError, ValueError):
        return default
    return max(1, min(d, 90))


def _parse_statuses(value, default=None):
    """Akceptuje string 'done,confirmed' lub listę; zwraca listę statusów slotów.
    Pusta wartość => [] (oznacza: WSZYSTKIE odbyte zajęcia, czyli każdy status poza 'cancelled')."""
    if isinstance(value, list):
        value = ','.join(str(v) for v in value)
    if value is None or not str(value).strip():
        value = default or ''
    return [s.strip() for s in str(value).split(',') if s.strip()]


def _find_missing_journal_entries(firma_id, days, statuses=None):
    """
    Znajduje odbyte zajęcia (schedule_slots, kind='therapy') bez wpisu w dzienniku
    (dziennik.data = dzień zajęć). Gdy 'statuses' jest puste, liczone są WSZYSTKIE
    odbyte zajęcia (każdy status poza 'cancelled') — zajęcia przeszłe często pozostają
    ze statusem 'planned', więc filtrowanie po 'done' pomijało część osób.
    Zwraca listę słowników pogrupowanych per terapeuta.
    """
    since = (datetime.now(TZ) - timedelta(days=days)).date()
    today = datetime.now(TZ).date()
    status_list = _parse_statuses(statuses)
    params = {'fid': firma_id, 'since': since, 'today': today}
    if status_list:
        placeholders = ', '.join(f':st{i}' for i in range(len(status_list)))
        status_cond = f"AND ss.status IN ({placeholders})"
        for i, s in enumerate(status_list):
            params[f'st{i}'] = s
    else:
        status_cond = "AND ss.status != 'cancelled'"

    sql = text(f"""
        SELECT ss.id AS slot_id,
               ss.therapist_id,
               t.full_name AS therapist_name,
               t.email AS therapist_email,
               ss.client_id,
               c.full_name AS client_name,
               (ss.starts_at AT TIME ZONE 'Europe/Warsaw')::date AS dzien
        FROM schedule_slots ss
        JOIN therapists t ON t.id = ss.therapist_id
        LEFT JOIN clients c ON c.id = ss.client_id
        WHERE ss.firma_id = :fid
          AND ss.kind = 'therapy'
          {status_cond}
          AND ss.therapist_id IS NOT NULL
          AND ss.client_id IS NOT NULL
          AND (ss.starts_at AT TIME ZONE 'Europe/Warsaw')::date >= :since
          AND (ss.starts_at AT TIME ZONE 'Europe/Warsaw')::date < :today
          AND NOT EXISTS (
              SELECT 1
              FROM dziennik d
              WHERE d.firma_id = :fid
                AND d.therapist_id = ss.therapist_id
                AND d.client_id = ss.client_id
                AND d.data = (ss.starts_at AT TIME ZONE 'Europe/Warsaw')::date
          )
        ORDER BY dzien DESC, therapist_name, client_name
    """)

    with engine.connect() as conn:
        rows = conn.execute(sql, params).mappings().all()

    therapists = {}
    for r in rows:
        entry = therapists.setdefault(r['therapist_id'], {
            'therapist_id': r['therapist_id'],
            'therapist_name': r['therapist_name'],
            'email': r['therapist_email'],
            'missing_count': 0,
            'missing': []
        })
        entry['missing_count'] += 1
        entry['missing'].append({
            'slot_id': r['slot_id'],
            'date': r['dzien'].isoformat() if r['dzien'] else None,
            'client_id': r['client_id'],
            'client_name': r['client_name']
        })
    return list(therapists.values())


@app.route('/api/dziennik/missing-entries', methods=['GET'])
@login_required
def dziennik_missing_entries():
    """
    Podgląd brakujących wpisów w dzienniku zajęć (bez wysyłki e-mail).
    Parametry: ?days=7 (1-90), ?statuses=done,confirmed (puste = wszystkie poza anulowanymi)
    """
    if not _can_manage_journal_reminders():
        return jsonify({'error': 'Brak uprawnień (wymagany admin, sekretariat lub uprawnienie "dziennik").'}), 403

    days = _parse_days(request.args.get('days'), default=7)
    statuses = request.args.get('statuses')
    firma_id = session.get('firma_id', 1)

    try:
        result = _find_missing_journal_entries(firma_id, days, statuses)
        total = sum(t['missing_count'] for t in result)
        return jsonify({
            'days': days,
            'statuses': _parse_statuses(statuses) or ['wszystkie poza anulowanymi'],
            'total_missing': total,
            'therapists': result
        }), 200
    except Exception as e:
        print(f"❌ Błąd pobierania brakujących wpisów dziennika: {e}")
        traceback.print_exc()
        return jsonify({'error': str(e)}), 500


@app.route('/api/dziennik/remind-therapists', methods=['POST'])
@login_required
def dziennik_remind_therapists():
    """
    Wysyła e-mailowe przypomnienie terapeutom o konieczności uzupełnienia wpisów
    w dzienniku zajęć dla odbytych zajęć bez wpisu (dla bieżącego podmiotu z sesji).
    Body (opcjonalnie): {"days": 7, "statuses": "done,confirmed", "dry_run": false}
    (puste 'statuses' = wszystkie odbyte zajęcia poza anulowanymi)
    """
    if not _can_manage_journal_reminders():
        return jsonify({'error': 'Brak uprawnień (wymagany admin, sekretariat lub uprawnienie "dziennik").'}), 403

    data = request.get_json(silent=True) or {}
    days = _parse_days(data.get('days', request.args.get('days')), default=7)
    statuses = data.get('statuses', request.args.get('statuses'))
    dry_run = bool(data.get('dry_run', False)) or request.args.get('dry_run') in ('1', 'true', 'True')
    firma_id = session.get('firma_id', 1)

    journal_url = request.host_url.rstrip('/') + '/klient_panel/dziennik'

    try:
        stats, therapists = _send_journal_reminders_for_firma(
            firma_id, days=days, statuses=statuses, dry_run=dry_run, journal_url=journal_url
        )
        log_activity(
            "PRZYPOMNIENIE_DZIENNIK_TERAPEUTOM",
            f"{'DRY RUN — ' if dry_run else ''}Wysłano {stats['sent']} przypomnień "
            f"({stats['missing_total']} brakujących wpisów, {stats['therapists_with_missing']} terapeutów, "
            f"zakres {days} dni)."
        )
        return jsonify({'success': True, **stats, 'therapists': therapists}), 200

    except Exception as e:
        print(f"❌ Błąd wysyłania przypomnień o dzienniku: {e}")
        traceback.print_exc()
        return jsonify({'error': str(e)}), 500


def _send_journal_reminders_for_firma(firma_id, days=7, statuses=None, dry_run=False, journal_url=None):
    """
    Wysyła e-mailowe przypomnienia o brakujących wpisach w dzienniku zajęć
    dla JEDNEGO podmiotu (firma_id). Działa także POZA kontekstem żądania
    (używane przez endpoint /api/dziennik/remind-therapists ORAZ przez scheduler).
    Zwraca krotkę (stats, therapists).
    """
    if not journal_url:
        journal_url = (os.environ.get('SITE_URL') or 'http://localhost:5000').rstrip('/') + '/klient_panel/dziennik'

    therapists = _find_missing_journal_entries(firma_id, days, statuses)
    stats = {
        'days': days,
        'statuses': _parse_statuses(statuses) or ['wszystkie poza anulowanymi'],
        'dry_run': dry_run,
        'therapists_with_missing': len(therapists),
        'missing_total': sum(t['missing_count'] for t in therapists),
        'sent': 0,
        'would_send': 0,
        'no_email': 0,
        'failed': 0
    }

    for t in therapists:
        email = (t['email'] or '').strip()
        name = t['therapist_name'] or f"Terapeuta #{t['therapist_id']}"

        if not email or '@' not in email:
            stats['no_email'] += 1
            print(f"⚠️ Brak e-maila u terapeuty {name} — pomijam przypomnienie ({t['missing_count']} brakujących wpisów).")
            continue

        items_html = ''.join(
            f"<li><strong>{html.escape(m['date'] or '')}</strong> — "
            f"{html.escape(m['client_name'] or ('klient #' + str(m['client_id'])))}</li>"
            for m in t['missing']
        )
        subject = f"Przypomnienie: uzupełnij wpisy w dzienniku zajęć ({t['missing_count']} brakujących)"
        body = f"""
        <html>
          <body>
            <h2>Witaj {html.escape(name)},</h2>
            <p>W systemie brakuje wpisów w <strong>dzienniku zajęć</strong> za następujące odbyte zajęcia:</p>
            <ul>{items_html}</ul>
            <p>Prosimy o jak najszybsze uzupełnienie wpisów: <a href="{journal_url}">{journal_url}</a></p>
            <p>Pozdrawiamy,<br/>System zarządzania placówką</p>
          </body>
        </html>
        """

        if dry_run:
            stats['would_send'] += 1
            print(f"🧪 DRY RUN — przypomnienie do {email} ({t['missing_count']} wpisów): {subject}")
        else:
            try:
                send_email_async(email, subject, body)
                stats['sent'] += 1
            except Exception as e:
                stats['failed'] += 1
                print(f"❌ Błąd wysyłki przypomnienia do {email}: {e}")

    return stats, therapists


# ==============================================================================
# === AUTOMATYCZNE PRZYPOMNIENIA O DZIENNIKU — HARMONOGRAM ZMIENNY (domyślnie piątek 9:00 Europe/Warsaw) ===
# ==============================================================================

# Konfiguracja automatu — to tylko WARTOŚCI DOMYŚLNE (można nadpisać zmiennymi środowiskowymi).
# Harmonogram (dzień tygodnia / godzina / włączenie) można zmieniać ręcznie w runtime przez
# API /api/admin/journal-reminder-schedule — zapis w tabeli app_settings, bez restartu aplikacji.
try:
    JOURNAL_REMINDER_DAYS = max(1, min(int(os.environ.get('JOURNAL_REMINDER_DAYS', '7')), 90))
except ValueError:
    JOURNAL_REMINDER_DAYS = 7
JOURNAL_REMINDER_STATUSES = os.environ.get('JOURNAL_REMINDER_STATUSES', '')

JOURNAL_SCHEDULE_KEY = 'journal_reminder_schedule'
_DOW_MAP = {'mon': 0, 'monday': 0, 'pon': 0,
            'tue': 1, 'tuesday': 1, 'wto': 1,
            'wed': 2, 'wednesday': 2, 'sro': 2,
            'thu': 3, 'thursday': 3, 'czw': 3,
            'fri': 4, 'friday': 4, 'pia': 4,
            'sat': 5, 'saturday': 5, 'sob': 5,
            'sun': 6, 'sunday': 6, 'nie': 6}
_DOW_NAMES = ['mon', 'tue', 'wed', 'thu', 'fri', 'sat', 'sun']


def _parse_dow(value, default=4):
    """Zamienia dzień tygodnia ('fri', 'piątek', 'pia', 4) na numer 0=poniedziałek .. 6=niedziela."""
    if value is None:
        return default
    if isinstance(value, int):
        return value % 7
    v = unidecode(str(value).strip().lower())
    if v in _DOW_MAP:
        return _DOW_MAP[v]
    if v.isdigit():
        return int(v) % 7
    raise ValueError(f"Nieprawidłowy dzień tygodnia: {value!r} (dozwolone: mon..sun, pon..nie, 0-6)")


def _default_journal_reminder_config():
    """Domyślna konfiguracja automatu przypomnień (ze zmiennych środowiskowych)."""
    return {
        'enabled': True,
        'day_of_week': 4,  # piątek
        'hour': 9,
        'minute': 0,
        'days': JOURNAL_REMINDER_DAYS,
        'statuses': JOURNAL_REMINDER_STATUSES,
    }


def _get_journal_reminder_config():
    """Konfiguracja automatu: domyślne + nadpisane z tabeli app_settings (klucz journal_reminder_schedule)."""
    cfg = _default_journal_reminder_config()
    try:
        with engine.connect() as conn:
            row = conn.execute(
                text("SELECT value FROM app_settings WHERE key = :k"), {'k': JOURNAL_SCHEDULE_KEY}
            ).mappings().first()
        if row and row['value']:
            saved = json.loads(row['value'])
            for k in ('enabled', 'day_of_week', 'hour', 'minute', 'days', 'statuses'):
                if k in saved:
                    cfg[k] = saved[k]
    except Exception as e:
        print(f"⚠️ Nie udało się odczytać harmonogramu przypomnień z bazy (używam domyślnych): {e}")
    cfg['enabled'] = bool(cfg.get('enabled', True))
    cfg['day_of_week'] = _parse_dow(cfg.get('day_of_week'), 4)
    cfg['hour'] = max(0, min(23, int(cfg.get('hour', 9))))
    cfg['minute'] = max(0, min(59, int(cfg.get('minute', 0))))
    cfg['days'] = _parse_days(cfg.get('days'), JOURNAL_REMINDER_DAYS)
    cfg['statuses'] = ','.join(_parse_statuses(cfg.get('statuses'), JOURNAL_REMINDER_STATUSES))
    return cfg


def _save_journal_reminder_config(save):
    """Zapisuje konfigurację harmonogramu do app_settings (klucz journal_reminder_schedule)."""
    with session_scope() as db_session:
        setting = db_session.query(AppSetting).filter_by(key=JOURNAL_SCHEDULE_KEY).first()
        if not setting:
            setting = AppSetting(key=JOURNAL_SCHEDULE_KEY, value=json.dumps(save))
            db_session.add(setting)
        else:
            setting.value = json.dumps(save)


def _next_scheduled_run(now, cfg):
    """Następny termin biegu wg konfiguracji (Europe/Warsaw); None, gdy automat jest wyłączony."""
    if not cfg.get('enabled', True):
        return None
    now = now or datetime.now(TZ)
    dow = _parse_dow(cfg.get('day_of_week'), 4)
    hour = max(0, min(23, int(cfg.get('hour', 9))))
    minute = max(0, min(59, int(cfg.get('minute', 0))))
    days_ahead = (dow - now.weekday()) % 7
    candidate = (now + timedelta(days=days_ahead)).replace(hour=hour, minute=minute, second=0, microsecond=0)
    if candidate <= now:
        candidate += timedelta(days=7)
    return candidate


def run_journal_reminder_job(days=None, statuses=None):
    """
    Zadanie automatyczne: wysyła przypomnienia o brakujących wpisach w dzienniku zajęć
    dla WSZYSTKICH podmiotów (firma) w systemie. Można też wywołać ręcznie (np. z testów).
    """
    days = JOURNAL_REMINDER_DAYS if days is None else _parse_days(days, JOURNAL_REMINDER_DAYS)
    statuses = JOURNAL_REMINDER_STATUSES if statuses is None else statuses

    total = {'firms': 0, 'sent': 0, 'would_send': 0, 'no_email': 0, 'failed': 0,
             'missing_total': 0, 'therapists_with_missing': 0}

    # Blokada na poziomie PostgreSQL (advisory lock, per sesja): przy wielu workerach
    # gunicorna tylko JEDEN worker wykonuje wysyłkę w danym biegu — pozostali pomijają.
    lock_conn = None
    try:
        lock_conn = engine.connect()
        locked = lock_conn.execute(
            text("SELECT pg_try_advisory_lock(hashtext('journal_reminder_friday_9am'))")
        ).scalar()
        if not locked:
            print("⏰ Scheduler dziennika: blokada zajęta przez innego workera — pomijam bieg.")
            return {'skipped_locked': True, **total}
        firma_ids = [row[0] for row in lock_conn.execute(text("SELECT id FROM firma ORDER BY id")).fetchall()]
    except Exception as e:
        print(f"❌ Scheduler dziennika: nie udało się pobrać listy firm: {e}")
        firma_ids = [1]

    try:
        for fid in firma_ids:
            try:
                stats, _therapists = _send_journal_reminders_for_firma(fid, days=days, statuses=statuses)
                total['firms'] += 1
                for k in ('sent', 'would_send', 'no_email', 'failed', 'missing_total', 'therapists_with_missing'):
                    total[k] += stats.get(k, 0)
            except Exception as e:
                print(f"❌ Scheduler dziennika: błąd dla firma_id={fid}: {e}")
                traceback.print_exc()

        log_activity(
            "PRZYPOMNIENIE_DZIENNIK_AUTOMAT",
            f"Automatyczne przypomnienia o dzienniku (piątek 9:00): firmy={total['firms']}, "
            f"wysłano={total['sent']}, brakujących wpisów={total['missing_total']}, "
            f"terapeutów={total['therapists_with_missing']}, bez e-maila={total['no_email']}, błędy={total['failed']}"
        )
        print(f"⏰ Scheduler dziennika — podsumowanie biegu: {total}")
        return total
    finally:
        if lock_conn is not None:
            try:
                lock_conn.execute(text("SELECT pg_advisory_unlock(hashtext('journal_reminder_friday_9am'))"))
            except Exception:
                pass
            lock_conn.close()


def _journal_reminder_scheduler_loop():
    """
    Pętla wątku: uruchamia run_journal_reminder_job() w terminie z konfiguracji
    (domyślnie piątek 9:00 Europe/Warsaw). Zmiana harmonogramu przez API
    /api/admin/journal-reminder-schedule działa bez restartu — konfiguracja
    jest odświeżana co 5 min.
    """
    while True:
        try:
            cfg = _get_journal_reminder_config()
            now = datetime.now(TZ)
            next_run = _next_scheduled_run(now, cfg)
            if next_run is None:
                print("⏰ Scheduler przypomnień o dzienniku: WYŁĄCZONY (enabled=false) — "
                      "sprawdzam zmiany konfiguracji co 5 min.")
                sleep(300)
                continue
            print(f"⏰ Scheduler przypomnień o dzienniku: następny bieg {next_run.strftime('%Y-%m-%d %H:%M %Z')} "
                  f"(za {(next_run - now).total_seconds() / 3600:.1f} h).")
            # Czekaj do następnego biegu, ale co 5 min odświeżaj konfigurację,
            # żeby ręczna zmiana harmonogramu weszła bez restartu aplikacji
            while True:
                remaining = (next_run - datetime.now(TZ)).total_seconds()
                if remaining <= 0:
                    break
                sleep(min(remaining, 300))
                new_next = _next_scheduled_run(datetime.now(TZ), _get_journal_reminder_config())
                if new_next != next_run:
                    next_run = new_next
                    if next_run is None:
                        break
                    print(f"⏰ Scheduler: zmieniono harmonogram — następny bieg {next_run.strftime('%Y-%m-%d %H:%M %Z')}.")
            if next_run is not None and (next_run - datetime.now(TZ)).total_seconds() <= 0:
                run_journal_reminder_job(days=cfg.get('days'), statuses=cfg.get('statuses'))
        except Exception as e:
            print(f"❌ Błąd w pętli schedulera przypomnień o dzienniku: {e}")
            traceback.print_exc()
            sleep(3600)  # przy błędzie poczekaj godzinę i kontynuuj


_journal_reminder_thread = None


# ==============================================================================
# === RĘCZNA ZMIANA HARMONOGRAMU WYSYŁKI AUTOMATYCZNEJ (admin, bez restartu) ===
# ==============================================================================

from flask import render_template_string  # prosty formularz admina osadzony w app.py


@app.route('/api/admin/journal-reminder-schedule', methods=['GET'])
@admin_required
def journal_reminder_schedule_get():
    """Aktualny harmonogram automatycznych przypomnień o dzienniku + następny zaplanowany bieg."""
    cfg = _get_journal_reminder_config()
    next_run = _next_scheduled_run(datetime.now(TZ), cfg)
    return jsonify({
        **cfg,
        'day_of_week_name': _DOW_NAMES[cfg['day_of_week']],
        'next_run': next_run.isoformat() if next_run else None,
        'scheduler_thread_alive': bool(
            (_journal_reminder_thread and _journal_reminder_thread.is_alive())
            or (_firma_reminder_thread and _firma_reminder_thread.is_alive())
        ),
    }), 200


@app.route('/api/admin/journal-reminder-schedule', methods=['PUT', 'POST'])
@admin_required
def journal_reminder_schedule_set():
    """
    Zmienia harmonogram automatycznej wysyłki — działa od razu, bez restartu aplikacji.
    Body (wszystkie pola opcjonalne): {"enabled": true, "day_of_week": "fri" (lub 4 / "piątek"),
    "hour": 9, "minute": 0, "days": 7, "statuses": "done,confirmed"}
    """
    data = request.get_json(silent=True) or {}
    try:
        cfg = _get_journal_reminder_config()
        if 'enabled' in data:
            cfg['enabled'] = bool(data['enabled'])
        if 'day_of_week' in data:
            cfg['day_of_week'] = _parse_dow(data['day_of_week'], cfg['day_of_week'])
        if 'hour' in data:
            cfg['hour'] = max(0, min(23, int(data['hour'])))
        if 'minute' in data:
            cfg['minute'] = max(0, min(59, int(data['minute'])))
        if 'days' in data:
            cfg['days'] = _parse_days(data['days'], cfg['days'])
        if 'statuses' in data:
            cfg['statuses'] = ','.join(_parse_statuses(data['statuses']))
    except (ValueError, TypeError) as e:
        return jsonify({'error': str(e)}), 400

    save = {k: cfg[k] for k in ('enabled', 'day_of_week', 'hour', 'minute', 'days', 'statuses')}
    try:
        _save_journal_reminder_config(save)
    except Exception as e:
        print(f"❌ Błąd zapisu harmonogramu przypomnień: {e}")
        return jsonify({'error': f'Nie udało się zapisać ustawień: {e}'}), 500

    log_activity("ZMIANA_HARMONOGRAMU_PRZYPOMNIEN",
                 f"Nowy harmonogram: dzień={_DOW_NAMES[save['day_of_week']]} "
                 f"{save['hour']:02d}:{save['minute']:02d}, enabled={save['enabled']}, "
                 f"days={save['days']}, statuses={save['statuses']}")
    next_run = _next_scheduled_run(datetime.now(TZ), _get_journal_reminder_config())
    return jsonify({'success': True, 'schedule': save,
                    'next_run': next_run.isoformat() if next_run else None}), 200


@app.route('/api/admin/journal-reminder-schedule/run-now', methods=['POST'])
@admin_required
def journal_reminder_run_now():
    """Ręczne, jednorazowe uruchomienie wysyłki przypomnień o dzienniku (poza harmonogramem, w tle)."""
    data = request.get_json(silent=True) or {}
    days = _parse_days(data['days'], None) if data.get('days') is not None else None
    statuses = data.get('statuses')
    threading.Thread(
        target=run_journal_reminder_job,
        kwargs={'days': days, 'statuses': statuses},
        name='journal-reminder-manual',
        daemon=True,
    ).start()
    log_activity("PRZYPOMNIENIE_DZIENNIK_RECZNE",
                 f"Ręczne uruchomienie wysyłki przypomnień (days={days}, statuses={statuses})")
    return jsonify({'success': True,
                    'message': 'Wysyłka uruchomiona w tle — wynik w logach (PRZYPOMNIENIE_DZIENNIK_AUTOMAT).'}), 202


@app.route('/admin/harmonogram-przypomnien', methods=['GET'])
@admin_required
def journal_reminder_schedule_page():
    """Prosty formularz do ręcznej zmiany harmonogramu automatycznej wysyłki maili."""
    return render_template_string("""<!doctype html>
<html lang="pl">
<head>
<meta charset="utf-8">
<title>Harmonogram przypomnień o dzienniku</title>
<style>
  body { font-family: sans-serif; max-width: 640px; margin: 40px auto; padding: 0 16px; color: #222; }
  h1 { font-size: 22px; }
  label { display: inline-block; margin: 8px 16px 8px 0; }
  input[type=number] { width: 70px; }
  button { margin-top: 12px; padding: 8px 16px; cursor: pointer; }
  #status { margin: 12px 0; padding: 10px; background: #f4f4f4; border-radius: 6px; white-space: pre-wrap; }
</style>
</head>
<body>
<h1>Harmonogram automatycznej wysyłki</h1>
<p>Przypomnienia e-mail o brakujących wpisach w dzienniku zajęć dla terapeutów.
Zmiana działa od razu, bez restartu aplikacji.</p>
<div id="status">Wczytywanie konfiguracji...</div>
<form id="cfg">
  <label><input type="checkbox" id="enabled"> Włączone</label>
  <label>Dzień tygodnia
    <select id="day_of_week">
      <option value="0">Poniedziałek</option>
      <option value="1">Wtorek</option>
      <option value="2">Środa</option>
      <option value="3">Czwartek</option>
      <option value="4">Piątek</option>
      <option value="5">Sobota</option>
      <option value="6">Niedziela</option>
    </select>
  </label>
  <label>Godzina <input type="number" id="hour" min="0" max="23"></label>
  <label>Minuta <input type="number" id="minute" min="0" max="59"></label>
  <br>
  <label>Zakres dni wstecz <input type="number" id="days" min="1" max="90"></label>
  <label>Statusy sesji <input type="text" id="statuses" placeholder="done,confirmed" size="20"></label>
  <br>
  <button type="submit">Zapisz harmonogram</button>
  <button type="button" id="runNow">Wyślij teraz (ręcznie)</button>
</form>
<script>
async function loadCfg() {
  const r = await fetch('/api/admin/journal-reminder-schedule');
  const cfg = await r.json();
  document.getElementById('enabled').checked = !!cfg.enabled;
  document.getElementById('day_of_week').value = String(cfg.day_of_week);
  document.getElementById('hour').value = cfg.hour;
  document.getElementById('minute').value = cfg.minute;
  document.getElementById('days').value = cfg.days;
  document.getElementById('statuses').value = cfg.statuses;
  document.getElementById('status').textContent =
    'Następny automatyczny bieg: ' + (cfg.next_run || 'automat wyłączony') +
    '\\nWątek schedulera aktywny: ' + cfg.scheduler_thread_alive;
}
document.getElementById('cfg').addEventListener('submit', async function (e) {
  e.preventDefault();
  const body = {
    enabled: document.getElementById('enabled').checked,
    day_of_week: parseInt(document.getElementById('day_of_week').value, 10),
    hour: parseInt(document.getElementById('hour').value, 10),
    minute: parseInt(document.getElementById('minute').value, 10),
    days: parseInt(document.getElementById('days').value, 10),
    statuses: document.getElementById('statuses').value
  };
  const r = await fetch('/api/admin/journal-reminder-schedule', {
    method: 'PUT',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify(body)
  });
  const res = await r.json();
  document.getElementById('status').textContent = r.ok
    ? 'Zapisano. Następny bieg: ' + (res.next_run || 'automat wyłączony')
    : 'Błąd: ' + (res.error || r.status);
});
document.getElementById('runNow').addEventListener('click', async function () {
  const r = await fetch('/api/admin/journal-reminder-schedule/run-now', { method: 'POST' });
  const res = await r.json();
  document.getElementById('status').textContent = res.message || JSON.stringify(res);
});
loadCfg();
</script>
</body>
</html>""")

ALLOWED_FREQUENCIES = {"disabled", "daily", "weekly", "biweekly", "monthly"}


def _get_or_create_settings(db_session, firma_id):
    s = db_session.query(FirmaSettings).filter_by(firma_id=firma_id).first()
    if not s:
        s = FirmaSettings(firma_id=firma_id)
        db_session.add(s)
        db_session.flush()
    return s


@admin_bp.route("/api/admin/firma-settings/journal-reminder", methods=["GET"])
@admin_required
def get_journal_reminder_settings():
    firma_id = session.get("firma_id", 1)
    try:
        with session_scope() as db:
            if not db.query(Firma.id).filter_by(id=firma_id).first():
                return jsonify({"error": f"Podmiot o id={firma_id} nie istnieje — wyloguj się i zaloguj ponownie."}), 404
            s = _get_or_create_settings(db, firma_id)
            return jsonify(s.as_dict()), 200
    except Exception as e:
        print(f"❌ Błąd get_journal_reminder_settings: {e}")
        traceback.print_exc()
        return jsonify({"error": str(e), "exception": type(e).__name__}), 500


@admin_bp.route("/api/admin/firma-settings/journal-reminder", methods=["PUT"])
@admin_required
def update_journal_reminder_settings():
    firma_id = session.get("firma_id", 1)
    data = request.get_json(silent=True) or {}

    freq = (data.get("journal_reminder_frequency") or "").strip()
    if freq not in ALLOWED_FREQUENCIES:
        return jsonify({"error": f"Nieprawidłowa częstotliwość. Dozwolone: {sorted(ALLOWED_FREQUENCIES)}"}), 400

    weekday = data.get("journal_reminder_weekday")
    hour = data.get("journal_reminder_hour")
    email_override = (data.get("journal_reminder_email_override") or "").strip() or None

    if freq != "disabled":
        try:
            weekday = int(weekday) if weekday is not None else 5
            hour = int(hour) if hour is not None else 9
        except (TypeError, ValueError):
            return jsonify({"error": "weekday i hour muszą być liczbami"}), 400
        if not (1 <= weekday <= 7):
            return jsonify({"error": "weekday musi być 1-7"}), 400
        if not (0 <= hour <= 23):
            return jsonify({"error": "hour musi być 0-23"}), 400

    try:
        with session_scope() as db:
            if not db.query(Firma.id).filter_by(id=firma_id).first():
                return jsonify({"error": f"Podmiot o id={firma_id} nie istnieje — wyloguj się i zaloguj ponownie."}), 404
            s = _get_or_create_settings(db, firma_id)
            s.journal_reminder_frequency = freq
            if freq != "disabled":
                s.journal_reminder_weekday = weekday
                s.journal_reminder_hour = hour
            s.journal_reminder_email_override = email_override

        log_activity(
            "FIRMA_SETTINGS_UPDATE",
            f"Zmieniono częstotliwość przypomnień o dzienniku na '{freq}' (firma {firma_id})",
        )
        return jsonify({"success": True}), 200
    except Exception as e:
        print(f"❌ Błąd update_journal_reminder_settings: {e}")
        traceback.print_exc()
        return jsonify({"error": str(e)}), 500

# =============================================================================
# PRZYPOMNIENIA O DZIENNIKU — tylko ten jeden typ maila
# =============================================================================

def _get_missing_journal_entries_for_firma(firma_id):
    """
    Zwraca listę stringów opisujących BRAKUJĄCE wpisy w dzienniku.
    Każda odbyta sesja 'therapy' (status inny niż 'cancelled') bez rekordu
    w tabeli dziennik w ostatnich 14 dniach.
    """
    with session_scope() as db:
        rows = db.execute(
            text("""
                SELECT s.id, s.starts_at, s.therapist_id, t.full_name AS therapist_name, c.full_name AS client_name
                FROM schedule_slots s
                JOIN clients c ON c.id = s.client_id
                JOIN therapists t ON t.id = s.therapist_id
                LEFT JOIN dziennik d
                  ON d.therapist_id = s.therapist_id
                 AND d.client_id    = s.client_id
                 AND d.firma_id     = s.firma_id
                 AND d.data = (s.starts_at AT TIME ZONE 'Europe/Warsaw')::date
                WHERE s.firma_id = :fid
                  AND s.kind     = 'therapy'
                  AND s.status  != 'cancelled'
                  AND s.therapist_id IS NOT NULL
                  AND d.id IS NULL
                  AND s.starts_at >= (NOW() - INTERVAL '14 days')
                ORDER BY s.starts_at DESC
            """),
            {"fid": firma_id},
        ).mappings().all()

        return [
            f"{r['starts_at'].strftime('%Y-%m-%d %H:%M')} — {r['client_name']}"
            for r in rows
        ]


def _send_journal_reminder_for_firma(firma_id, settings_row):
    """
    Wysyła JEDEN mail o brakujących wpisach w dzienniku.
    Żadnych innych powiadomień — tylko dziennik.
    """
    # 1. Sprawdź, czy w ogóle są braki
    missing = _get_missing_journal_entries_for_firma(firma_id)
    if not missing:
        # Brak braków — tylko aktualizujemy znacznik, żeby nie sprawdzać co chwilę
        with session_scope() as db:
            s = db.query(FirmaSettings).filter_by(firma_id=firma_id).first()
            if s:
                s.last_journal_reminder_sent_at = datetime.now(TZ)
        return

    # 2. Zbierz odbiorców: admini firmy + opcjonalny override z ustawień
    recipients = set()
    with session_scope() as db:
        admins = (
            db.query(User)
            .filter(User.firma_id == firma_id, User.is_admin.is_(True))
            .all()
        )
        for a in admins:
            if a.email:
                recipients.add(a.email.strip())

    if settings_row and settings_row.journal_reminder_email_override:
        for part in re.split(r"[,;]", settings_row.journal_reminder_email_override):
            if part.strip():
                recipients.add(part.strip())

    if not recipients:
        print(f"⚠️ Firma {firma_id}: brak odbiorców (admini bez e-maila, brak override).")
        return

    # 3. Treść maila — WYŁĄCZNIE o dzienniku
    subject = "Zaległe wpisy w dzienniku — prosimy o uzupełnienie"
    preview_items = "".join(f"<li>{html.escape(m)}</li>" for m in missing[:20])
    html_body = f"""
    <html><body style="font-family: Arial, sans-serif;">
      <h2>Zaległe wpisy w dzienniku</h2>
      <p>W systemie wykryto <strong>{len(missing)}</strong> sesji terapeutycznych,
         dla których nie uzupełniono jeszcze wpisu w dzienniku.</p>
      <ul>{preview_items}</ul>
      {"<p><em>…i więcej.</em></p>" if len(missing) > 20 else ""}
      <p>Prosimy o zalogowanie się do systemu i uzupełnienie wpisów.</p>
      <hr>
      <p style="color:#888; font-size:12px;">Wiadomość wygenerowana automatycznie przez system Centrum.</p>
    </body></html>
    """

    # 4. Wysyłka
    sent_count = 0
    for addr in recipients:
        if send_email_sync(addr, subject, html_body):
            sent_count += 1

    # 5. Aktualizacja znacznika
    with session_scope() as db:
        s = db.query(FirmaSettings).filter_by(firma_id=firma_id).first()
        if s:
            s.last_journal_reminder_sent_at = datetime.now(TZ)

    log_activity(
        "JOURNAL_REMINDER_SENT",
        f"Wysłano przypomnienie o dzienniku do firmy {firma_id} "
        f"({sent_count}/{len(recipients)} maili, braków: {len(missing)}).",
    )

def _should_send_now(settings, now_warsaw):
    freq = (settings.journal_reminder_frequency or "weekly").lower()
    if freq == "disabled":
        return False
    if now_warsaw.isoweekday() != (settings.journal_reminder_weekday or 5):
        return False
    if now_warsaw.hour != (settings.journal_reminder_hour or 9):
        return False

    last = settings.last_journal_reminder_sent_at
    if last is not None:
        if last.tzinfo is None:
            last = last.replace(tzinfo=TZ)
        delta = now_warsaw - last
        if freq == "daily"    and delta < timedelta(hours=23):  return False
        if freq == "weekly"   and delta < timedelta(days=6):    return False
        if freq == "biweekly" and delta < timedelta(days=13):   return False
        if freq == "monthly"  and delta < timedelta(days=27):   return False
    return True


def get_firms_to_remind_now(now_warsaw=None):
    if now_warsaw is None:
        now_warsaw = datetime.now(TZ)
    result = []
    with session_scope() as db:
        settings_rows = (db.query(FirmaSettings)
                         .filter(FirmaSettings.journal_reminder_frequency != "disabled")
                         .all())
        for s in settings_rows:
            if _should_send_now(s, now_warsaw):
                result.append((s.firma_id, s))
    return result


def run_firma_journal_reminder_job():
    """
    Wysyła zbiorcze maile o zaległościach w dzienniku do adminów podmiotów,
    zgodnie z częstotliwością ustawioną per podmiot (FirmaSettings / tabela firma_settings,
    edytowalna z dashboardu przez /api/admin/firma-settings/journal-reminder).
    Wywoływane cyklicznie przez wątek _firma_reminder_scheduler_loop.
    """
    try:
        pairs = get_firms_to_remind_now()
    except Exception as e:
        print(f"❌ Scheduler dziennika (ustawienia podmiotów): błąd pobierania podmiotów: {e}")
        traceback.print_exc()
        return {'error': str(e)}
    sent = 0
    for firma_id, settings_row in pairs:
        try:
            _send_journal_reminder_for_firma(firma_id, settings_row)
            sent += 1
        except Exception as e:
            print(f"❌ Scheduler dziennika (ustawienia podmiotów): błąd dla firma_id={firma_id}: {e}")
            traceback.print_exc()
    if pairs:
        print(f"⏰ Scheduler dziennika (ustawienia podmiotów): wysyłka dla {sent}/{len(pairs)} podmiotów.")
    return {'firms': len(pairs), 'sent': sent}


def _firma_reminder_scheduler_loop():
    """Pętla wątku: co 5 minut sprawdza, czy któryś podmiot ma zaplanowaną wysyłkę (dzień+godzina), i wysyła."""""
    while True:
        try:
            run_firma_journal_reminder_job()
        except Exception as e:
            print(f"❌ Błąd w pętli schedulera (ustawienia podmiotów): {e}")
            traceback.print_exc()
        sleep(300)


_firma_reminder_thread = None








@app.context_processor
def inject_journal_warning():
    """
    Sprawdza, czy zalogowany terapeuta ma zaległe dzienniki do wypełnienia.
    Zmienna 'has_missing_journals' będzie automatycznie dostępna we wszystkich szablonach HTML.
    """
    if not current_user.is_authenticated:
        return {'has_missing_journals': False}
    
    # Pobieramy ID terapeuty powiązanego z aktualnie zalogowanym użytkownikiem
    therapist_id = getattr(current_user, 'therapist_id', None)
    if not therapist_id:
        return {'has_missing_journals': False}
        
    try:
        with SessionLocal() as db_session:
            # Zapytanie szuka minionych sesji terapeuty, które nie mają wpisu w tabeli 'dziennik'
            query = text("""
                SELECT 1
                FROM schedule_slots s
                WHERE s.therapist_id = :tid
                  AND s.kind = 'therapy'
                  AND s.status != 'cancelled'
                  AND s.starts_at < NOW()
                  AND s.starts_at >= NOW() - INTERVAL '14 days'
                  AND NOT EXISTS (
                      SELECT 1 FROM dziennik d 
                      WHERE d.therapist_id = :tid 
                        AND d.data = (s.starts_at AT TIME ZONE 'Europe/Warsaw')::date
                  )
                LIMIT 1
            """)
            missing = db_session.execute(query, {"tid": therapist_id}).scalar()
            return {'has_missing_journals': bool(missing)}
            
    except Exception as e:
        print(f"❌ Błąd sprawdzania zaległych dzienników dla usera: {e}")
        return {'has_missing_journals': False}


def start_journal_reminder_scheduler():
    """Startuje (jednorazowo, idempotentnie) dwa wątki schedulera:
    1) przypomnienia do terapeutów wg globalnego harmonogramu (domyślnie piątek 9:00),
    2) zbiorcze maile do adminów wg częstotliwości ustawionej per podmiot (firma_settings)."""
    global _journal_reminder_thread, _firma_reminder_thread
    if _journal_reminder_thread is None or not _journal_reminder_thread.is_alive():
        _journal_reminder_thread = threading.Thread(
            target=_journal_reminder_scheduler_loop,
            name='journal-reminder-scheduler',
            daemon=True
        )
        _journal_reminder_thread.start()
        print("✓ Scheduler przypomnień o dzienniku zajęć uruchomiony (każdy piątek 9:00 Europe/Warsaw).")
    if _firma_reminder_thread is None or not _firma_reminder_thread.is_alive():
        _firma_reminder_thread = threading.Thread(
            target=_firma_reminder_scheduler_loop,
            name='firma-reminder-scheduler',
            daemon=True
        )
        _firma_reminder_thread.start()
        print("✓ Scheduler przypomnień (ustawienia podmiotów) uruchomiony (kontrola co 5 minut).")
    return _journal_reminder_thread


@app.before_request
def _ensure_journal_reminder_scheduler():
    """Awaryjny start schedulera przy pierwszym żądaniu (np. gdy aplikacja działa pod gunicorn, bez __main__)."""
    start_journal_reminder_scheduler()


# === Uruchomienie aplikacji ===



app.register_blueprint(auth_bp, url_prefix="")
app.register_blueprint(admin_bp, url_prefix="")

# ← tutaj scheduler (raz przy starcie)
start_journal_reminder_scheduler()


app.register_blueprint(kadry_bp)

if not init_all_tables():
    print("KRYTYCZNY BŁĄD: Nie udało się zainicjalizować tabel. Aplikacja zatrzymana.")

if __name__ == '__main__':
    init_documents_table()
    # app.run(debug=True) poniżej włącza reloader Werkzeuga, który wykonuje skrypt w dwóch
    # procesach (rodzic + dziecko). Scheduler przypomnień o dzienniku startujemy tylko
    # w procesie roboczym serwera (WERKZEUG_RUN_MAIN=true), żeby nie wysłać ich podwójnie.
    # Gdy aplikacja działa bez __main__ (np. gunicorn), scheduler wystartuje przy pierwszym
    # żądaniu przez @app.before_request (_ensure_journal_reminder_scheduler).
    if os.environ.get('WERKZEUG_RUN_MAIN') == 'true':
        start_journal_reminder_scheduler()
    app.run(debug=False, host='0.0.0.0', port=5000)














