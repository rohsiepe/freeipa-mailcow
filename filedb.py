import datetime, os

import logging
logging.basicConfig(format='%(asctime)s %(message)s', datefmt='%d.%m.%y %H:%M:%S', level=logging.INFO)

import sqlalchemy
from sqlalchemy.ext.declarative import declarative_base
from sqlalchemy import create_engine, Column, String, Boolean, DateTime
from sqlalchemy.orm import sessionmaker

from pathlib import Path

db_file = 'db/freeipa-mailcow.sqlite3'

Base = declarative_base()

class DbUser(Base): # type: ignore
    __tablename__ = 'users'
    email = Column(String, primary_key=True)
    active = Column(Boolean, nullable=False)
    last_seen = Column(DateTime, nullable=False)

Session = sessionmaker()

if not os.path.isfile(db_file):
    logging.info (f"New database file created: {db_file}")
    Path(os.path.dirname(db_file)).mkdir(parents=True, exist_ok=True)

db_engine = create_engine(f"sqlite:///{db_file}") # echo=True
Base.metadata.create_all(db_engine)
Session.configure(bind=db_engine)
session = Session()
session_time = datetime.datetime.now()

def get_unchecked_active_emails():
    query = session.query(DbUser.email).filter(DbUser.last_seen != session_time).filter(DbUser.active == True)
    return [x.email for x in query]

def add_user(uid, maildomain, active=True):
    email = uid + '@' + maildomain
    session.add(DbUser(email=email, active=active, last_seen=session_time))
    session.commit()

def check_user(uid, maildomain):
    email = uid + '@' + maildomain
    user = session.query(DbUser).filter_by(email=email).first()
    if user is None:
        return (False, False)
    user.last_seen = session_time
    session.commit()
    return (True, user.active)

def user_set_active_to(uid, maildomain, active):
    email = uid + '@' + maildomain
    user = session.query(DbUser).filter_by(email=email).first()
    user.active = active
    session.commit()