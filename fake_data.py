import datetime
import json
import os
import random
import re

from faker import Faker

_FAKE = Faker()


def _load_birth_year_range():
    cfg_path = os.path.join(os.path.dirname(__file__), 'config.json')
    ymin, ymax = 1980, 2004
    try:
        with open(cfg_path, 'r') as f:
            cfg = json.load(f)
        ymin = int(cfg.get('birth_year_min', ymin))
        ymax = int(cfg.get('birth_year_max', ymax))
    except Exception:
        pass
    if ymin > ymax:
        ymin, ymax = ymax, ymin
    return ymin, ymax


def _random_birth_date():
    ymin, ymax = _load_birth_year_range()
    year = random.randint(ymin, ymax)
    month = random.randint(1, 12)
    if month == 2:
        leap = (year % 4 == 0 and (year % 100 != 0 or year % 400 == 0))
        max_day = 29 if leap else 28
    elif month in (4, 6, 9, 11):
        max_day = 30
    else:
        max_day = 31
    day = random.randint(1, max_day)
    return datetime.date(year, month, day)


def generate_fake_data():
    long_login = ''.join(e for e in (_FAKE.user_name() * 10) if e.isalnum())
    while not long_login or not long_login[0].isalpha():
        long_login = ''.join(e for e in (_FAKE.user_name() * 10) if e.isalnum())

    login_length = random.randint(13, 25)
    login = long_login[:login_length]

    password = _FAKE.password(length=random.randint(13, 25), special_chars=False)
    while len(re.findall(r"\d", password)) < 2:
        password = _FAKE.password(length=random.randint(13, 25), special_chars=False)

    first_name = _FAKE.first_name()
    last_name = _FAKE.last_name()
    birth_date = _random_birth_date()

    return login, password, first_name, last_name, birth_date
