#!/usr/bin/env python3
"""
МинералКарта — Сервер
Run: python3 server.py
Access: http://localhost:3000
"""

import sqlite3
import hashlib
import secrets
import json
import os
import time
import functools
import urllib.request
import uuid
from flask import Flask, request, jsonify, send_from_directory, send_file, Response
from werkzeug.utils import secure_filename
import jwt

# ─── CONFIG ───────────────────────────────────────────────────────────────────

DB_PATH = os.path.join(os.path.dirname(__file__), 'mines.db')
JWT_SECRET = 'mineralKarta_secret_key_2024_kazakh_mines'
STATIC_DIR = os.path.join(os.path.dirname(__file__), 'public')
UPLOAD_DIR = os.path.join(os.path.dirname(__file__), 'uploads')
PORT = int(os.environ.get('PORT', 3000))

ALLOWED_IMAGE_EXT = {'jpg', 'jpeg', 'png', 'gif', 'webp'}
ALLOWED_VIDEO_EXT = {'mp4', 'webm', 'mov', 'avi', 'mkv'}

app = Flask(__name__, static_folder=STATIC_DIR)
app.config['MAX_CONTENT_LENGTH'] = 200 * 1024 * 1024  # 200 MB

def allowed_file(filename):
    ext = filename.rsplit('.', 1)[-1].lower() if '.' in filename else ''
    return ext, ext in (ALLOWED_IMAGE_EXT | ALLOWED_VIDEO_EXT)

def media_type_from_ext(ext):
    return 'photo' if ext in ALLOWED_IMAGE_EXT else 'video'

# ─── DATABASE ─────────────────────────────────────────────────────────────────

def get_db():
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA foreign_keys = ON")
    return conn

def init_db():
    conn = get_db()
    c = conn.cursor()

    c.executescript("""
        CREATE TABLE IF NOT EXISTS users (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            username TEXT UNIQUE NOT NULL,
            password_hash TEXT NOT NULL,
            salt TEXT NOT NULL,
            created_at DATETIME DEFAULT CURRENT_TIMESTAMP
        );

        CREATE TABLE IF NOT EXISTS mines (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            user_id INTEGER,
            name TEXT NOT NULL,
            type TEXT NOT NULL,
            status TEXT NOT NULL,
            depth_m INTEGER DEFAULT 0,
            year_opened INTEGER,
            description TEXT,
            lat REAL NOT NULL,
            lng REAL NOT NULL,
            ph REAL,
            mineralization REAL,
            conductivity REAL,
            hardness REAL,
            temperature_c REAL,
            sediment TEXT,
            water_quality TEXT,
            created_at DATETIME DEFAULT CURRENT_TIMESTAMP,
            FOREIGN KEY (user_id) REFERENCES users(id)
        );

        CREATE TABLE IF NOT EXISTS notes (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            mine_id INTEGER NOT NULL,
            user_id INTEGER NOT NULL,
            content TEXT NOT NULL,
            created_at DATETIME DEFAULT CURRENT_TIMESTAMP,
            FOREIGN KEY (mine_id) REFERENCES mines(id) ON DELETE CASCADE,
            FOREIGN KEY (user_id) REFERENCES users(id)
        );

        CREATE TABLE IF NOT EXISTS media (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            mine_id INTEGER NOT NULL,
            user_id INTEGER NOT NULL,
            filename TEXT NOT NULL,
            original_name TEXT,
            media_type TEXT NOT NULL,
            created_at DATETIME DEFAULT CURRENT_TIMESTAMP,
            FOREIGN KEY (mine_id) REFERENCES mines(id) ON DELETE CASCADE,
            FOREIGN KEY (user_id) REFERENCES users(id)
        );
    """)

    for col, typedef in [
        ('ph', 'REAL'), ('mineralization', 'REAL'), ('conductivity', 'REAL'),
        ('hardness', 'REAL'), ('temperature_c', 'REAL'), ('sediment', 'TEXT'), ('water_quality', 'TEXT'),
        ('region', 'TEXT'), ('district', 'TEXT'),
    ]:
        try:
            c.execute(f"ALTER TABLE mines ADD COLUMN {col} {typedef}")
        except Exception:
            pass
    conn.commit()

    row = c.execute("SELECT COUNT(*) as cnt FROM mines").fetchone()
    if row['cnt'] == 0:
        seed_data(conn)

    conn.close()

def hash_password(password):
    salt = secrets.token_hex(32)
    h = hashlib.pbkdf2_hmac('sha256', password.encode(), salt.encode(), 200000)
    return h.hex(), salt

def verify_password(password, stored_hash, salt):
    h = hashlib.pbkdf2_hmac('sha256', password.encode(), salt.encode(), 200000)
    return h.hex() == stored_hash

def seed_data(conn):
    c = conn.cursor()

    pw_hash, pw_salt = hash_password('admin123')
    c.execute("INSERT OR IGNORE INTO users (username, password_hash, salt) VALUES (?,?,?)",
              ('admin', pw_hash, pw_salt))
    admin = c.execute("SELECT id FROM users WHERE username='admin'").fetchone()
    admin_id = admin['id']

    # (name, type, status, lat, lng, depth_m, year, description, [notes])
    springs = [
        # ── АЛМАТИНСКАЯ ОБЛАСТЬ ──────────────────────────────────────────────
        ('Алма-Арасан', 'Источник', 'Активный', 43.08, 76.91, 0, 1868,
         'Термоминеральный источник в горах Заилийского Алатау, в 25 км от Алматы. '
         'Температура воды +36–42°C, богата кремниевой кислотой и радоном.',
         ['Известен с середины XIX века, упоминается в записках русских путешественников.',
          'Вода относится к классу слабоминерализованных радоновых вод.',
          'На базе источника работает бальнеологический санаторий.']),

        ('Иссык (Есік)', 'Родник', 'Активный', 43.27, 77.47, 0, 1920,
         'Горный родник у подножия хребта Заилийский Алатау близ посёлка Иссык. '
         'Питает одноимённую реку, впадающую в Капчагайское водохранилище.',
         ['Вода прозрачная, холодная, освежает в летний зной.',
          'Рядом расположено знаменитое озеро Иссык, образовавшееся в результате оползня.']),

        ('Тургень', 'Родник', 'Активный', 43.24, 78.01, 0, 1900,
         'Родник в Тургеньском ущелье Алматинской области. '
         'Ущелье богато водопадами и родниками с чистейшей горной водой.',
         ['Один из популярных маршрутов для пешего туризма в окрестностях Алматы.',
          'Вода соответствует нормам питьевого водоснабжения по всем показателям.']),

        ('Каинды', 'Родник', 'Активный', 43.05, 78.37, 0, 1911,
         'Родник у высокогорного озера Каинды (Карасай), образовавшегося после землетрясения 1911 года. '
         'Высота — около 2000 м над уровнем моря.',
         ['Озеро и родники — объекты природного наследия Алматинской области.',
          'Вода ледниково-родниковая, температура не превышает +5°C.']),

        ('Чарын', 'Родник', 'Активный', 43.35, 79.09, 0, 1950,
         'Родники вдоль берегов реки Чарын в одноимённом каньоне. '
         'Каньон глубиной до 300 м — природный памятник Казахстана.',
         ['Родники питают редкую реликтовую ясеневую рощу.',
          'Вода выходит из трещин осадочных пород мелового периода.']),

        ('Чунджа (горячие)', 'Источник', 'Активный', 43.57, 80.52, 0, 1960,
         'Система из 140 термальных источников в Уйгурском районе Алматинской области. '
         'Температура воды +37–50°C. Воды хлоридно-натриевые.',
         ['Используются местным населением для лечебных ванн.',
          'Несколько источников благоустроены под купальни.']),

        ('Капчагай', 'Родник', 'Активный', 43.87, 77.07, 0, 1970,
         'Пресноводный родник на берегу Капчагайского водохранилища. '
         'Популярное место отдыха жителей Алматы.',
         ['Родник сохраняет стабильный дебит даже при сильной летней жаре.',
          'Вода прошла лабораторный контроль, пригодна для питья.']),

        ('Медеу', 'Родник', 'Активный', 43.13, 77.06, 0, 1955,
         'Горный родник у знаменитого высокогорного катка Медеу (1691 м). '
         'Вода используется для питьевых нужд спортивного комплекса.',
         ['Температура воды круглогодично держится около +4°C.',
          'Родник расположен в зоне особо охраняемого природного комплекса.']),

        # ── ВОСТОЧНО-КАЗАХСТАНСКАЯ ОБЛАСТЬ ──────────────────────────────────
        ('Рахмановские ключи', 'Источник', 'Активный', 49.48, 86.15, 0, 1769,
         'Радоновые термоминеральные источники на правом берегу р. Арасан в Катон-Карагайском районе. '
         'Открыты крестьянином Рахмановым в 1769 г. Из гранитной скалы вытекает 12 родников, '
         'температура воды +34–43°C.',
         ['Один из старейших бальнеологических курортов Казахстана и Центральной Азии.',
          'Вода содержит кремниевую кислоту и слабую радиоактивность природного происхождения.',
          'Высота расположения — 1760 м над уровнем моря.']),

        ('Катон-Карагай', 'Родник', 'Активный', 49.33, 85.63, 0, 1850,
         'Горный родник в Катон-Карагайском национальном парке (ВКО). '
         'Один из самых чистых природных источников Алтайской горной системы.',
         ['Вода используется жителями пос. Катон-Карагай для питьевых нужд.',
          'Родник не замерзает даже в суровые зимы ВКО.']),

        ('Маркаколь', 'Родник', 'Активный', 49.07, 85.66, 0, 1900,
         'Ключевые родники на берегах высокогорного озера Маркаколь (1449 м). '
         'Озеро и его родники входят в состав одноимённого заповедника.',
         ['Вода кристально чистая, без запаха и цвета.',
          'Заповедник — Рамсарское угодье международного значения.']),

        ('Белуха (подножие)', 'Родник', 'Активный', 49.80, 86.58, 0, 1935,
         'Родники у подножия горы Белуха (4506 м) — высочайшей точки Казахстана и Алтая. '
         'Питаются ледниковыми талыми водами.',
         ['Белуха — священная гора для народов Алтая.',
          'Вода имеет ледниковое происхождение, температура близка к 0°C.']),

        ('Зыряновск (Алтай)', 'Источник', 'Активный', 49.74, 84.27, 0, 1790,
         'Минеральный источник в Западно-Алтайском заповеднике близ г. Риддер (Лениногорск). '
         'История использования местным населением — более 200 лет.',
         ['Воды слабоминерализованные, используются в лечебных целях.',
          'Рядом расположен Западно-Алтайский государственный природный заповедник.']),

        # ── ТУРКЕСТАНСКАЯ ОБЛАСТЬ ────────────────────────────────────────────
        ('Аксу-Жабаглы', 'Родник', 'Активный', 42.37, 70.61, 0, 1920,
         'Горные родники в Аксу-Жабаглинском заповеднике — старейшем заповеднике '
         'Центральной Азии (осн. 1926). Расположен в Таласском Алатау.',
         ['Заповедник входит в список Всемирного природного наследия ЮНЕСКО.',
          'Родники питают реки Аксу и Жабаглы.',
          'Вода используется для научных гидрологических наблюдений.']),

        ('Арыстан-Баб', 'Родник', 'Активный', 42.29, 69.96, 0, 1100,
         'Сакральный родник у мавзолея Арыстан-Баба (XI–XII вв.) в Туркестанской области. '
         'Считается священным у паломников и местных жителей.',
         ['Мавзолей и родник — объекты религиозного и исторического значения.',
          'Вода источника, по преданию, обладает целебными свойствами.',
          'Ежегодно родник посещают тысячи паломников.']),

        ('Байдибек', 'Родник', 'Активный', 42.43, 69.72, 0, 1800,
         'Родник в Туркестанской области, известный в народе как «живая вода». '
         'Назван в честь легендарного батыра Байдибека.',
         ['Вода используется местным населением для питьевых нужд.',
          'Рядом возведена небольшая мечеть и беседка для паломников.']),

        ('Жабаглы', 'Источник', 'Активный', 42.52, 70.79, 0, 1930,
         'Минеральный источник на территории Аксу-Жабаглинского заповедника. '
         'Вода сульфатно-кальциевая, используется в научных исследованиях.',
         ['Источник расположен на высоте около 1200 м над уровнем моря.',
          'Является объектом гидрогеологического мониторинга.']),

        # ── ЖАМБЫЛСКАЯ ОБЛАСТЬ ──────────────────────────────────────────────
        ('Аулие-Ата (Тараз)', 'Родник', 'Активный', 42.90, 71.37, 0, 800,
         'Священный родник в окрестностях Тараза (Жамбылская обл.). '
         'Название «Аулие-Ата» переводится как «Святой дед/предок».',
         ['Один из сакральных объектов Жамбылской области.',
          'Вода почитается верующими, к роднику совершаются паломничества.']),

        ('Мерке', 'Родник', 'Активный', 42.87, 73.18, 0, 1900,
         'Родник в долине реки Мерке (Жамбылская область). '
         'Питается подземными водами предгорий Киргизского Алатау.',
         ['Дебит родника — около 1 л/с, не зависит от сезона.',
          'Вода используется для орошения садов и огородов.']),

        ('Айша-Биби', 'Родник', 'Активный', 42.78, 71.09, 0, 1100,
         'Родник у мавзолея Айша-Биби (XI–XII вв.) — памятника архитектуры близ Тараза. '
         'Считается символом вечной любви в казахской народной традиции.',
         ['Мавзолей — объект Всемирного наследия под охраной ЮНЕСКО.',
          'Родник не пересыхал на протяжении всего известного периода истории.']),

        # ── АКМОЛИНСКАЯ ОБЛАСТЬ ─────────────────────────────────────────────
        ('Буработ (Бурабай)', 'Родник', 'Активный', 53.09, 70.30, 0, 1820,
         'Родник в курортной зоне Бурабай («Казахстанская Швейцария»), '
         'Акмолинская область. Питается за счёт просачивания атмосферных осадков через '
         'гранитные породы Кокшетауского массива.',
         ['Бурабай — главный рекреационный район Казахстана.',
          'Родник облагорожен, рядом установлены беседки и информационные щиты.',
          'Вода слабоминерализованная, рекомендована к питью.']),

        ('Имантау', 'Родник', 'Активный', 53.08, 69.70, 0, 1900,
         'Родник на берегу озера Имантау (Акмолинская обл.). '
         'Питает небольшой ручей, впадающий в озеро.',
         ['Озеро Имантау известно лечебными грязями.',
          'Родник не пересыхает даже в засушливые годы.']),

        ('Карасу (Акмола)', 'Родник', 'Активный', 52.30, 70.80, 0, 1910,
         'Родник «Карасу» (чёрная вода) в степях Акмолинской области. '
         'Название отражает высокое содержание органических веществ.',
         ['Является важным водопоем для скота и диких животных в степи.',
          'Дебит сезонный, наибольший — весной и в начале лета.']),

        ('Степняк', 'Родник', 'Закрыт', 52.36, 71.89, 0, 1896,
         'Исторический родник в посёлке Степняк (Акмолинская обл.), известный с XIX века. '
         'Иссяк в начале 1990-х годов в результате нарушения водоносного горизонта.',
         ['Родник был главным источником питьевой воды для старательских посёлков.',
          'В 1991 году зафиксировано полное прекращение выхода воды на поверхность.']),

        # ── ПАВЛОДАРСКАЯ ОБЛАСТЬ ────────────────────────────────────────────
        ('Баянаул', 'Родник', 'Активный', 50.79, 75.70, 0, 1850,
         'Родники в Баянаульском национальном природном парке (Павлодарская обл.). '
         'Расположены среди гранитных сопок Казахского мелкосопочника.',
         ['Национальный парк основан в 1985 году.',
          'Вода родников питает озёра Жасыбай и Торайгыр.',
          'Ежегодно парк принимает более 150 000 туристов.']),

        ('Жасыбай', 'Родник', 'Активный', 50.74, 75.49, 0, 1900,
         'Подземный родник, питающий живописное озеро Жасыбай в Баянаульском парке. '
         'По народному преданию, у этого родника похоронен акын Жаяу Муса.',
         ['Вода прозрачная, прохладная, пригодна для питья.',
          'Озеро Жасыбай — одно из красивейших в Казахстане.']),

        # ── КАРАГАНДИНСКАЯ ОБЛАСТЬ ───────────────────────────────────────────
        ('Каркаралы', 'Родник', 'Активный', 49.43, 75.55, 0, 1870,
         'Родник в Каркаралинском национальном природном парке (Карагандинская обл.). '
         'Питается за счёт инфильтрации через гранитно-сланцевые породы сопок.',
         ['Парк основан в 1998 году на месте старейшего заповедника региона.',
          'Родник служит источником воды для туристических стоянок.']),

        ('Бектауата', 'Родник', 'Активный', 47.42, 75.72, 0, 1930,
         'Родник у скального массива Бектауата в Карагандинской области. '
         'Бектауата — сакральное место, «место силы» у казахов.',
         ['Скальный массив признан памятником природы республиканского значения.',
          'Вода холодная, выходит из трещин гранитных скал.']),

        ('Каражал', 'Родник', 'Активный', 47.97, 70.82, 0, 1950,
         'Родник в степях Карагандинской области близ г. Жезды. '
         'Один из немногих постоянных источников воды в засушливой зоне.',
         ['Родник используется пастухами и чабанами как водопой.',
          'Вода слегка минерализованная, без запаха.']),

        # ── ЖЕТЫСУСКАЯ / АЛМАТИНСКАЯ ─────────────────────────────────────────
        ('Алтын-Эмель', 'Родник', 'Активный', 43.62, 79.07, 0, 1960,
         'Родник в национальном парке Алтын-Эмель (Алматинская обл.). '
         'Питает небольшие озерки среди полупустынных саксауловых лесов.',
         ['Нац. парк — объект Всемирного природного наследия ЮНЕСКО.',
          'В парке обитают джейраны, архары, кулан — животные, занесённые в Красную книгу.']),

        ('Жаркент', 'Родник', 'Активный', 44.17, 80.03, 0, 1880,
         'Родник вблизи г. Жаркент (Алматинская обл., у границы с Китаем). '
         'Используется жителями города на протяжении более 100 лет.',
         ['Вода питьевая, соответствует санитарным нормам.',
          'Жаркент — исторический торговый город на Великом шёлковом пути.']),

        # ── ЖЕЗКАЗГАН / УЛЫТАУ ───────────────────────────────────────────────
        ('Улытау', 'Родник', 'Активный', 48.62, 67.03, 0, 1200,
         'Священный родник в горах Улытау («Великие горы») — сакральном центре казахского народа. '
         'Здесь проходили курылтаи казахских ханов.',
         ['Улытау — место захоронения казахских батыров и биев.',
          'Родник почитается как священный с древних времён.',
          'В 2022 году Улытау стал центром новообразованной одноимённой области.']),

        ('Жезды', 'Родник', 'Активный', 48.09, 67.72, 0, 1900,
         'Степной родник в Улытауской области близ посёлка Жезды. '
         'Один из немногих постоянных источников воды в засушливом регионе.',
         ['Родник используется как водопой для табунов лошадей.',
          'Дебит — около 0.3 л/с.']),

        # ── АКТЮБИНСКАЯ ОБЛАСТЬ ──────────────────────────────────────────────
        ('Хромтау (родник)', 'Родник', 'Активный', 50.28, 58.44, 0, 1930,
         'Родник у г. Хромтау Актюбинской области. '
         'Один из немногих пресных источников в полупустынной зоне.',
         ['Родник благоустроен местными жителями, установлен каптаж.',
          'Используется как место отдыха и пикников горожан.']),

        ('Саркырама', 'Источник', 'Активный', 50.87, 52.53, 0, 1910,
         'Степной водопад-родник Саркырама в Шынгырлауском районе ЗКО. '
         'Высота каскада — 4 м. Один из уникальных природных объектов западного Казахстана.',
         ['Родник и водопад — памятник природы регионального значения.',
          'Название «Саркырама» переводится как «журчащий» или «шумящий».',
          'Место паломничества и туристических поездок жителей ЗКО.']),

        # ── КОСТАНАЙСКАЯ ОБЛАСТЬ ─────────────────────────────────────────────
        ('Наурзум', 'Родник', 'Активный', 51.97, 64.57, 0, 1930,
         'Родник в Наурзумском государственном заповеднике (Костанайская обл.). '
         'Заповедник включён в список объектов Всемирного природного наследия ЮНЕСКО.',
         ['Заповедник — крупнейшее место гнездования редких птиц Казахстана.',
          'Родник питает систему озёр заповедника.',
          'Вода используется для орнитологических наблюдений и науки.']),

        ('Денисовка', 'Колодец', 'Активный', 52.63, 62.95, 35, 1890,
         'Старинный колодец в с. Денисовка Костанайской области. '
         'Возведён переселенцами в конце XIX века, используется по сей день.',
         ['Глубина колодца — 35 м, вода выходит на ур. грунтового горизонта.',
          'Является историческим памятником переселенческого быта XIX века.']),

        ('Торгай', 'Родник', 'Активный', 50.07, 65.37, 0, 1870,
         'Родник в долине реки Торгай (Костанайская обл.). '
         'Известен как место водопоя на старых казахских кочевых маршрутах.',
         ['Дебит весной достигает 2–3 л/с, летом снижается.',
          'Вблизи родника сохранились следы стоянок кочевников.']),

        # ── СЕВЕРО-КАЗАХСТАНСКАЯ ОБЛАСТЬ ────────────────────────────────────
        ('Петропавловск (Кызылжар)', 'Родник', 'Активный', 54.87, 69.15, 0, 1880,
         'Родник на берегу реки Ишим в окрестностях Петропавловска. '
         'Используется жителями города с конца XIX века.',
         ['Вода соответствует нормам питьевого водоснабжения.',
          'Родник расположен в парковой зоне города.']),

        ('Сергеевка (СКО)', 'Родник', 'Активный', 53.88, 67.65, 0, 1950,
         'Родник близ Сергеевского водохранилища в СКО. '
         'Питается подземными водами, инфильтрующимися из водохранилища.',
         ['Вода слабоминерализованная, пригодна для питья.',
          'Место отдыха жителей Петропавловска.']),

        # ── ВОСТОЧНО-КАЗАХСТАНСКАЯ / АЛТАЙ ───────────────────────────────────
        ('Риддер (Лениногорск)', 'Источник', 'Активный', 50.35, 83.52, 0, 1789,
         'Горные источники в районе Риддера (ВКО) — одни из старейших известных источников '
         'Рудного Алтая. Упомянуты в первых описаниях освоения Алтая в XVIII в.',
         ['Воды слабоминерализованные, обогащены горными минералами.',
          'Источник расположен в зоне Западно-Алтайского заповедника.']),

        # ── МАНГЫСТАУСКАЯ ОБЛАСТЬ ────────────────────────────────────────────
        ('Бекет-Ата', 'Родник', 'Активный', 43.21, 52.38, 0, 1800,
         'Сакральный родник у подземной мечети Бекет-Ата (XIX в.) на плато Мангышлак. '
         'Один из главных объектов паломничества в Казахстане.',
         ['Ежегодно мечеть посещают сотни тысяч паломников.',
          'Вода источника почитается как святая, люди привозят её домой.',
          'Расположен в урочище Огланды среди меловых скал.']),

        ('Шеркала', 'Родник', 'Активный', 43.58, 53.48, 0, 1900,
         'Родник у горы Шеркала («Львиная крепость») на Мангышлакском плато. '
         'Редкий источник пресной воды в засушливом Мангыстау.',
         ['Шеркала — природная достопримечательность Мангыстауской области.',
          'Родник — важный ориентир для туристов и путников.']),

        # ── АТЫРАУСКАЯ ОБЛАСТЬ ──────────────────────────────────────────────
        ('Атырау (степной)', 'Родник', 'Законсервирован', 47.12, 51.88, 0, 1910,
         'Степной родник в Атырауской области в дельте Урала. '
         'Законсервирован в 1980-х гг. в связи с загрязнением нефтепродуктами.',
         ['Родник расположен в зоне активной нефтедобычи.',
          'Взят под охрану природоохранными органами для возможного восстановления.']),

        # ── КЫЗЫЛОРДИНСКАЯ ОБЛАСТЬ ──────────────────────────────────────────
        ('Байконыр (степной)', 'Родник', 'Активный', 45.62, 63.32, 0, 1920,
         'Небольшой родник в степях Кызылординской области близ Байконура. '
         'Один из немногих постоянных источников пресной воды в Приаралье.',
         ['Служит водопоем для диких животных в полупустынной зоне.',
          'Воды слабосолоноватые, пригодны для животных, но не для питья.']),

        ('Арысь', 'Родник', 'Активный', 42.43, 68.80, 0, 1900,
         'Родник в долине реки Арысь (Туркестанская обл.). '
         'Питает одноимённую реку, впадающую в Сырдарью.',
         ['Вода пресная, используется для полива сельскохозяйственных угодий.',
          'Долина реки Арысь — один из плодородных оазисов юга Казахстана.']),

        # ── ЗАПАДНО-КАЗАХСТАНСКАЯ ОБЛАСТЬ ────────────────────────────────────
        ('Уральск (Орал)', 'Колодец', 'Активный', 51.23, 51.37, 25, 1830,
         'Исторический колодец в старой части г. Уральск (ЗКО). '
         'Возведён казаками в XIX веке, реставрирован в 2010 году.',
         ['Является историческим памятником казачьего освоения степи.',
          'Глубина — 25 м, вода подходит для хозяйственных нужд.']),
    ]

    wq_data = {
        'Медеу':             {'ph': 7.5, 'mineralization': 160,  'conductivity': 220,  'hardness': 2.8, 'temperature_c': 7.0,  'sediment': 'Нет'},
        'Иссык (Есік)':      {'ph': 7.2, 'mineralization': 130,  'conductivity': 190,  'hardness': 1.9, 'temperature_c': 6.0,  'sediment': 'Нет'},
        'Тургень':           {'ph': 7.4, 'mineralization': 145,  'conductivity': 210,  'hardness': 2.3, 'temperature_c': 8.0,  'sediment': 'Нет'},
        'Каинды':            {'ph': 7.1, 'mineralization': 110,  'conductivity': 165,  'hardness': 1.5, 'temperature_c': 4.0,  'sediment': 'Нет'},
        'Буработ (Бурабай)': {'ph': 7.3, 'mineralization': 180,  'conductivity': 295,  'hardness': 2.1, 'temperature_c': 9.0,  'sediment': 'Нет'},
        'Баянаул':           {'ph': 7.3, 'mineralization': 200,  'conductivity': 325,  'hardness': 2.9, 'temperature_c': 10.0, 'sediment': 'Нет'},
        'Каркаралы':         {'ph': 7.1, 'mineralization': 175,  'conductivity': 280,  'hardness': 2.7, 'temperature_c': 8.0,  'sediment': 'Нет'},
        'Алма-Арасан':       {'ph': 7.2, 'mineralization': 480,  'conductivity': 780,  'hardness': 4.2, 'temperature_c': 38.0, 'sediment': 'Нет'},
        'Рахмановские ключи':{'ph': 7.0, 'mineralization': 520,  'conductivity': 880,  'hardness': 5.1, 'temperature_c': 40.0, 'sediment': 'Нет'},
        'Чунджа (горячие)':  {'ph': 7.8, 'mineralization': 650,  'conductivity': 1100, 'hardness': 5.8, 'temperature_c': 44.0, 'sediment': 'Нет'},
        'Бекет-Ата':         {'ph': 7.6, 'mineralization': 640,  'conductivity': 1050, 'hardness': 6.8, 'temperature_c': 18.0, 'sediment': 'Нет'},
        'Жабаглы':           {'ph': 7.9, 'mineralization': 580,  'conductivity': 960,  'hardness': 7.3, 'temperature_c': 12.0, 'sediment': 'Нет'},
        'Атырау (степной)':  {'ph': 7.6, 'mineralization': 1620, 'conductivity': 2700, 'hardness': 11.5,'temperature_c': 14.0, 'sediment': 'Есть'},
    }

    for (name, mtype, status, lat, lng, depth, year, desc, notes) in springs:
        wq = wq_data.get(name, {})
        ph_v = wq.get('ph'); min_v = wq.get('mineralization')
        cond_v = wq.get('conductivity'); hard_v = wq.get('hardness')
        r = c.execute(
            "INSERT INTO mines (user_id,name,type,status,lat,lng,depth_m,year_opened,description,"
            "ph,mineralization,conductivity,hardness,temperature_c,sediment,water_quality) VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)",
            (admin_id, name, mtype, status, lat, lng, depth, year, desc,
             ph_v, min_v, cond_v, hard_v,
             wq.get('temperature_c'), wq.get('sediment'),
             calc_water_quality(ph_v, min_v, cond_v, hard_v))
        )
        spring_id = r.lastrowid
        for note in notes:
            c.execute("INSERT INTO notes (mine_id,user_id,content) VALUES (?,?,?)",
                      (spring_id, admin_id, note))

    conn.commit()
    print(f"✅ Seed data inserted: {len(springs)} springs across Kazakhstan")

# ─── AUTH HELPERS ─────────────────────────────────────────────────────────────

def generate_token(user_id, username):
    payload = {
        'id': user_id,
        'username': username,
        'exp': time.time() + 7 * 24 * 3600
    }
    return jwt.encode(payload, JWT_SECRET, algorithm='HS256')

def decode_token(token):
    return jwt.decode(token, JWT_SECRET, algorithms=['HS256'])

def get_current_user():
    auth = request.headers.get('Authorization', '')
    if not auth.startswith('Bearer '):
        return None
    token = auth[7:]
    try:
        return decode_token(token)
    except Exception:
        return None

def require_auth(f):
    @functools.wraps(f)
    def wrapper(*args, **kwargs):
        user = get_current_user()
        if not user:
            return jsonify({'error': 'Токен не предоставлен или недействителен'}), 401
        request.current_user = user
        return f(*args, **kwargs)
    return wrapper

def calc_water_quality(ph, mineralization, conductivity, hardness):
    if all(v is None for v in [ph, mineralization, conductivity, hardness]):
        return None
    rejected = False
    analysis = False
    if ph is not None:
        if ph < 6.0 or ph > 9.5: rejected = True
        elif ph < 6.5 or ph > 8.5: analysis = True
    if mineralization is not None:
        if mineralization > 1500: rejected = True
        elif mineralization > 1000: analysis = True
    if conductivity is not None:
        if conductivity > 2500: rejected = True
        elif conductivity > 1500: analysis = True
    if hardness is not None:
        if hardness > 10: rejected = True
        elif hardness > 7: analysis = True
    if rejected: return 'Отклонён'
    if analysis: return 'Анализ'
    return 'Подходит'

def row_to_dict(row):
    return dict(row) if row else None

def rows_to_list(rows):
    return [dict(r) for r in rows]

TILE_CACHE_DIR = os.path.join(os.path.dirname(__file__), 'tile_cache')

TILE_SOURCES = [
    'https://core-renderer-tiles.maps.yandex.net/tiles?l=map&x={x}&y={y}&z={z}&scale=1&lang=ru_RU',
    'https://vec01.maps.yandex.net/tiles?l=map&x={x}&y={y}&z={z}&scale=1&lang=ru_RU',
    'https://vec02.maps.yandex.net/tiles?l=map&x={x}&y={y}&z={z}&scale=1&lang=ru_RU',
    'https://tile.openstreetmap.org/{z}/{x}/{y}.png',
    'https://a.basemaps.cartocdn.com/rastertiles/voyager/{z}/{x}/{y}.png',
]

# ─── TILE PROXY ───────────────────────────────────────────────────────────────

@app.route('/api/tiles/<int:z>/<int:x>/<int:y>.png')
def tile_proxy(z, x, y):
    if not (0 <= z <= 19):
        return '', 400
    max_coord = 2 ** z
    if not (0 <= x < max_coord and 0 <= y < max_coord):
        return '', 400

    cache_path = os.path.join(TILE_CACHE_DIR, str(z), str(x), f'{y}.png')
    if os.path.exists(cache_path):
        return send_file(cache_path, mimetype='image/png')

    for template in TILE_SOURCES:
        url = template.format(z=z, x=x, y=y)
        try:
            req = urllib.request.Request(url, headers={
                'User-Agent': 'MineralKarta/1.0 (educational mining map project)',
                'Accept': 'image/png,image/*',
            })
            with urllib.request.urlopen(req, timeout=8) as resp:
                if resp.status == 200:
                    data = resp.read()
                    os.makedirs(os.path.dirname(cache_path), exist_ok=True)
                    with open(cache_path, 'wb') as f:
                        f.write(data)
                    r = Response(data, mimetype='image/png')
                    r.headers['Cache-Control'] = 'public, max-age=86400'
                    return r
        except Exception:
            continue

    return '', 404

# ─── STATIC FILES ─────────────────────────────────────────────────────────────

@app.route('/')
def index():
    return send_file(os.path.join(STATIC_DIR, 'index.html'))

@app.route('/<path:path>')
def static_files(path):
    full = os.path.join(STATIC_DIR, path)
    if os.path.isfile(full):
        return send_from_directory(STATIC_DIR, path)
    return send_file(os.path.join(STATIC_DIR, 'index.html'))

# ─── AUTH ROUTES ──────────────────────────────────────────────────────────────

@app.route('/api/auth/register', methods=['POST'])
def register():
    data = request.json or {}
    username = (data.get('username') or '').strip()
    password = data.get('password') or ''

    if not username or not password:
        return jsonify({'error': 'Введите имя пользователя и пароль'}), 400
    if len(username) < 3:
        return jsonify({'error': 'Имя пользователя должно быть не менее 3 символов'}), 400
    if len(password) < 6:
        return jsonify({'error': 'Пароль должен быть не менее 6 символов'}), 400

    conn = get_db()
    try:
        existing = conn.execute("SELECT id FROM users WHERE username=?", (username,)).fetchone()
        if existing:
            return jsonify({'error': 'Пользователь с таким именем уже существует'}), 409

        pw_hash, pw_salt = hash_password(password)
        c = conn.execute("INSERT INTO users (username,password_hash,salt) VALUES (?,?,?)",
                         (username, pw_hash, pw_salt))
        conn.commit()
        user_id = c.lastrowid
        token = generate_token(user_id, username)
        return jsonify({'token': token, 'user': {'id': user_id, 'username': username}}), 201
    finally:
        conn.close()

@app.route('/api/auth/login', methods=['POST'])
def login():
    data = request.json or {}
    username = (data.get('username') or '').strip()
    password = data.get('password') or ''

    if not username or not password:
        return jsonify({'error': 'Введите имя пользователя и пароль'}), 400

    conn = get_db()
    try:
        user = conn.execute("SELECT * FROM users WHERE username=?", (username,)).fetchone()
        if not user or not verify_password(password, user['password_hash'], user['salt']):
            return jsonify({'error': 'Неверное имя пользователя или пароль'}), 401

        token = generate_token(user['id'], user['username'])
        return jsonify({'token': token, 'user': {'id': user['id'], 'username': user['username']}})
    finally:
        conn.close()

# ─── MINES ROUTES ─────────────────────────────────────────────────────────────

@app.route('/api/mines', methods=['GET'])
def get_mines():
    conn = get_db()
    try:
        rows = conn.execute("""
            SELECT m.*, u.username as owner_name,
            (SELECT COUNT(*) FROM notes n WHERE n.mine_id = m.id) as note_count
            FROM mines m
            LEFT JOIN users u ON u.id = m.user_id
            ORDER BY m.created_at DESC
        """).fetchall()
        return jsonify(rows_to_list(rows))
    finally:
        conn.close()

@app.route('/api/mines', methods=['POST'])
@require_auth
def create_mine():
    data = request.json or {}
    name = (data.get('name') or '').strip()
    mtype = data.get('type') or ''
    status = data.get('status') or ''
    depth = int(data.get('depth_m') or 0)
    year = data.get('year_opened')
    desc = (data.get('description') or '').strip()
    lat = data.get('lat')
    lng = data.get('lng')
    ph = data.get('ph')
    mineralization = data.get('mineralization')
    conductivity = data.get('conductivity')
    hardness = data.get('hardness')
    temperature_c = data.get('temperature_c')
    sediment = (data.get('sediment') or '').strip() or None
    region = (data.get('region') or '').strip() or None
    district = (data.get('district') or '').strip() or None
    water_quality = calc_water_quality(ph, mineralization, conductivity, hardness)

    if not name or not mtype or not status or lat is None or lng is None:
        return jsonify({'error': 'Заполните обязательные поля'}), 400

    valid_types = ['Родник', 'Источник', 'Колодец']
    valid_statuses = ['Активный', 'Законсервирован', 'Закрыт']

    if mtype not in valid_types:
        return jsonify({'error': 'Неверный тип объекта'}), 400
    if status not in valid_statuses:
        return jsonify({'error': 'Неверный статус'}), 400

    conn = get_db()
    try:
        c = conn.execute(
            "INSERT INTO mines (user_id,name,type,status,depth_m,year_opened,description,lat,lng,"
            "ph,mineralization,conductivity,hardness,temperature_c,sediment,water_quality,region,district) VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)",
            (request.current_user['id'], name, mtype, status, depth, year, desc, lat, lng,
             ph, mineralization, conductivity, hardness, temperature_c, sediment, water_quality,
             region, district)
        )
        conn.commit()
        mine = conn.execute("SELECT * FROM mines WHERE id=?", (c.lastrowid,)).fetchone()
        return jsonify(row_to_dict(mine)), 201
    finally:
        conn.close()

@app.route('/api/mines/<int:mine_id>', methods=['PUT'])
@require_auth
def update_mine(mine_id):
    conn = get_db()
    try:
        mine = conn.execute("SELECT * FROM mines WHERE id=?", (mine_id,)).fetchone()
        if not mine:
            return jsonify({'error': 'Объект не найден'}), 404
        if mine['user_id'] != request.current_user['id']:
            return jsonify({'error': 'Нет прав для редактирования'}), 403

        data = request.json or {}
        name = (data.get('name') or mine['name']).strip()
        mtype = data.get('type') or mine['type']
        status = data.get('status') or mine['status']
        depth = int(data.get('depth_m', mine['depth_m']) or 0)
        year = data.get('year_opened', mine['year_opened'])
        desc = data.get('description', mine['description']) or ''
        ph = data.get('ph', mine['ph'])
        mineralization = data.get('mineralization', mine['mineralization'])
        conductivity = data.get('conductivity', mine['conductivity'])
        hardness = data.get('hardness', mine['hardness'])
        temperature_c = data.get('temperature_c', mine['temperature_c'])
        sediment = data.get('sediment', mine['sediment'])
        region = data.get('region', mine['region'])
        district = data.get('district', mine['district'])
        if isinstance(region, str): region = region.strip() or None
        if isinstance(district, str): district = district.strip() or None
        water_quality = calc_water_quality(ph, mineralization, conductivity, hardness)

        conn.execute(
            "UPDATE mines SET name=?,type=?,status=?,depth_m=?,year_opened=?,description=?,"
            "ph=?,mineralization=?,conductivity=?,hardness=?,temperature_c=?,sediment=?,water_quality=?,"
            "region=?,district=? WHERE id=?",
            (name, mtype, status, depth, year, desc,
             ph, mineralization, conductivity, hardness, temperature_c, sediment, water_quality,
             region, district,
             mine_id)
        )
        conn.commit()
        updated = conn.execute("SELECT * FROM mines WHERE id=?", (mine_id,)).fetchone()
        return jsonify(row_to_dict(updated))
    finally:
        conn.close()

@app.route('/api/mines/<int:mine_id>', methods=['DELETE'])
@require_auth
def delete_mine(mine_id):
    conn = get_db()
    try:
        mine = conn.execute("SELECT * FROM mines WHERE id=?", (mine_id,)).fetchone()
        if not mine:
            return jsonify({'error': 'Объект не найден'}), 404
        if mine['user_id'] != request.current_user['id']:
            return jsonify({'error': 'Нет прав для удаления'}), 403

        media_rows = conn.execute("SELECT filename FROM media WHERE mine_id=?", (mine_id,)).fetchall()
        for row in media_rows:
            filepath = os.path.join(UPLOAD_DIR, row['filename'])
            if os.path.exists(filepath):
                try:
                    os.remove(filepath)
                except Exception:
                    pass

        conn.execute("DELETE FROM notes WHERE mine_id=?", (mine_id,))
        conn.execute("DELETE FROM media WHERE mine_id=?", (mine_id,))
        conn.execute("DELETE FROM mines WHERE id=?", (mine_id,))
        conn.commit()
        return jsonify({'message': 'Объект удалён'})
    finally:
        conn.close()

# ─── NOTES ROUTES ─────────────────────────────────────────────────────────────

@app.route('/api/mines/<int:mine_id>/notes', methods=['GET'])
def get_notes(mine_id):
    conn = get_db()
    try:
        rows = conn.execute("""
            SELECT n.*, u.username FROM notes n
            JOIN users u ON u.id = n.user_id
            WHERE n.mine_id=? ORDER BY n.created_at ASC
        """, (mine_id,)).fetchall()
        return jsonify(rows_to_list(rows))
    finally:
        conn.close()

@app.route('/api/mines/<int:mine_id>/notes', methods=['POST'])
@require_auth
def add_note(mine_id):
    data = request.json or {}
    content = (data.get('content') or '').strip()
    if not content:
        return jsonify({'error': 'Заметка не может быть пустой'}), 400

    conn = get_db()
    try:
        mine = conn.execute("SELECT id FROM mines WHERE id=?", (mine_id,)).fetchone()
        if not mine:
            return jsonify({'error': 'Объект не найден'}), 404

        c = conn.execute(
            "INSERT INTO notes (mine_id,user_id,content) VALUES (?,?,?)",
            (mine_id, request.current_user['id'], content)
        )
        conn.commit()
        note = conn.execute("""
            SELECT n.*, u.username FROM notes n
            JOIN users u ON u.id = n.user_id WHERE n.id=?
        """, (c.lastrowid,)).fetchone()
        return jsonify(row_to_dict(note)), 201
    finally:
        conn.close()

# ─── MEDIA ROUTES ─────────────────────────────────────────────────────────────

@app.route('/api/mines/<int:mine_id>/media', methods=['GET'])
def get_media(mine_id):
    conn = get_db()
    try:
        rows = conn.execute("""
            SELECT m.*, u.username FROM media m
            JOIN users u ON u.id = m.user_id
            WHERE m.mine_id=? ORDER BY m.created_at ASC
        """, (mine_id,)).fetchall()
        return jsonify(rows_to_list(rows))
    finally:
        conn.close()

@app.route('/api/mines/<int:mine_id>/media', methods=['POST'])
@require_auth
def upload_media(mine_id):
    conn = get_db()
    try:
        mine = conn.execute("SELECT id FROM mines WHERE id=?", (mine_id,)).fetchone()
        if not mine:
            return jsonify({'error': 'Объект не найден'}), 404

        if 'file' not in request.files:
            return jsonify({'error': 'Файл не выбран'}), 400

        file = request.files['file']
        if not file.filename:
            return jsonify({'error': 'Файл не выбран'}), 400

        original_name = secure_filename(file.filename)
        ext, ok = allowed_file(original_name)
        if not ok:
            return jsonify({'error': 'Недопустимый формат. Разрешены: jpg, png, gif, webp, mp4, webm, mov, avi, mkv'}), 400

        unique_name = f"{uuid.uuid4().hex}.{ext}"
        os.makedirs(UPLOAD_DIR, exist_ok=True)
        file.save(os.path.join(UPLOAD_DIR, unique_name))

        mtype = media_type_from_ext(ext)
        c = conn.execute(
            "INSERT INTO media (mine_id, user_id, filename, original_name, media_type) VALUES (?,?,?,?,?)",
            (mine_id, request.current_user['id'], unique_name, original_name, mtype)
        )
        conn.commit()

        row = conn.execute("""
            SELECT m.*, u.username FROM media m
            JOIN users u ON u.id = m.user_id WHERE m.id=?
        """, (c.lastrowid,)).fetchone()
        return jsonify(row_to_dict(row)), 201
    finally:
        conn.close()

@app.route('/api/mines/<int:mine_id>/media/<int:media_id>', methods=['DELETE'])
@require_auth
def delete_media(mine_id, media_id):
    conn = get_db()
    try:
        row = conn.execute("SELECT * FROM media WHERE id=? AND mine_id=?", (media_id, mine_id)).fetchone()
        if not row:
            return jsonify({'error': 'Файл не найден'}), 404

        mine = conn.execute("SELECT user_id FROM mines WHERE id=?", (mine_id,)).fetchone()
        if row['user_id'] != request.current_user['id'] and mine['user_id'] != request.current_user['id']:
            return jsonify({'error': 'Нет прав для удаления'}), 403

        filepath = os.path.join(UPLOAD_DIR, row['filename'])
        if os.path.exists(filepath):
            os.remove(filepath)

        conn.execute("DELETE FROM media WHERE id=?", (media_id,))
        conn.commit()
        return jsonify({'message': 'Файл удалён'})
    finally:
        conn.close()

@app.route('/uploads/<path:filename>')
def serve_upload(filename):
    return send_from_directory(UPLOAD_DIR, filename)

# ─── RUN ──────────────────────────────────────────────────────────────────────

if __name__ == '__main__':
    init_db()
    print(f"\n🪨  МинералКарта запущена на http://localhost:{PORT}")
    print(f"📦  База данных: mines.db")
    print(f"👤  Тестовый аккаунт: admin / admin123\n")
    app.run(host='0.0.0.0', port=int(os.environ.get('PORT', PORT)), debug=False)