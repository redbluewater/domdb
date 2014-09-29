import os
import csv
import json

import sqlalchemy
from sqlalchemy.ext.declarative import declarative_base
from sqlalchemy import Column, Integer, BigInteger, String, DateTime, Boolean, ForeignKey, Numeric, func, and_
from sqlalchemy.orm import sessionmaker, relationship, backref, aliased
from sqlalchemy.types import PickleType

# JSON serialization
class TextPickleType(PickleType):
    impl = String

Base = declarative_base()

class Metabolite(Base):
    __tablename__ = 'metabolite'

    id = Column(Integer, primary_key=True)
    experiment = Column(String) # experiment name
    mz = Column(Numeric) # mass-to-charge ratio
    mzmin = Column(Numeric)
    mzmax = Column(Numeric)
    rt = Column(Numeric) # retention time (seconds)
    rtmin = Column(Numeric)
    rtmax = Column(Numeric)
    rest = Column(TextPickleType(pickler=json))

    def __repr__(self):
        return '<Metabolite %s %s %s %s>' % (self.experiment, str(self.mz), str(self.rt), json.dumps(self.rest, sort_keys=True, indent=2))

def get_sqlite_engine(delete=True):
    # first, toast db
    DB_FILE = 'kuj2.db'
    if delete and os.path.exists(DB_FILE):
        try:
            os.remove(DB_FILE)
        except:
            print 'unable to delete %s' % DB_FILE
            raise
    return sqlalchemy.create_engine('sqlite:///%s' % DB_FILE)

COMMON_FIELDS=set(['mz','mzmin','mzmax','rt','rtmin','rtmax'])

def etl(session, exp_name, path):
    with open(path) as cf:
        r = csv.DictReader(cf)
        for d in r:
            # subset the fields
            keys = set(d.keys())
            rest_keys = keys.difference(COMMON_FIELDS)
            md = dict((k,d[k]) for k in COMMON_FIELDS)
            md['experiment'] = exp_name
            rest = dict((k,d[k]) for k in rest_keys if k)
            md['rest'] = rest
            # construct orm object
            m = Metabolite(**md)
            # add to session
            session.add(m)
    session.commit()

def etl_all(session):
    exp_file = {
        'tps4': 'Tps4_pos_2014.05.23.csv',
        'tps6': 'Tps6_pos_2014.05.23.csv'
    }
    for e,f in exp_file.items():
        etl(session, e, f)
    # now commit
    session.commit()

def match_all_from(session,exp,ppm_diff=0.5,rt_diff=30):
    m_alias = aliased(Metabolite)
    for m in session.query(Metabolite, m_alias).\
        join((m_alias, and_(Metabolite.id != m_alias.id, Metabolite.experiment != m_alias.experiment))).\
        filter(Metabolite.experiment == exp).\
        filter(func.abs(1e6 * (Metabolite.mz - m_alias.mz) / m_alias.mz) <= ppm_diff).\
        filter(func.abs(Metabolite.rt - m_alias.rt) <= rt_diff).\
        order_by(Metabolite.mz, m_alias.experiment):
        yield m
    
def match_all(session,ppm_diff=0.5,rt_diff=30):
    m_alias = aliased(Metabolite)
    for m in session.query(Metabolite, m_alias).\
        join((m_alias, Metabolite.id != m_alias.id)).\
        filter(func.abs(1e6 * (Metabolite.mz - m_alias.mz) / m_alias.mz) <= ppm_diff).\
        filter(func.abs(Metabolite.rt - m_alias.rt) <= rt_diff):
        yield m

def match_one(session,m,ppm_diff=0.5,rt_diff=30):
    for m in session.query(Metabolite).\
        filter(Metabolite.id != m.id).\
        filter(func.abs(1e6 * (Metabolite.mz - m.mz) / m.mz) <= ppm_diff).\
        filter(func.abs(Metabolite.rt - m.rt) <= rt_diff):
        yield m

def mtab_search(session,mz,rt,ppm_diff=0.5,rt_diff=30):
    for m in session.query(Metabolite).\
        filter(func.abs(1e6 * (mz - Metabolite.mz) / Metabolite.mz) <= ppm_diff).\
        filter(func.abs(rt - Metabolite.rt) <= rt_diff):
        yield m

def mtab_random(session):
    return session.query(Metabolite).order_by(func.random()).limit(1)[0]

if __name__=='__main__':
    engine = get_sqlite_engine()
    Base.metadata.create_all(engine)
    Session = sessionmaker()
    Session.configure(bind=engine)
    session = Session()
    print 'Loading data...'
    etl_all(session)
    # now count how many entries we have
    n = session.query(func.count(Metabolite.id)).first()[0]
    print '%d metabolites loaded' % n
    # now pick four metabolites at random
    for m in session.query(Metabolite).order_by(func.random()).limit(4):
        print 'Looking for matches for %s' % m
        # for each one, find matching ones
        for match in match_one(session,m):
            print 'Match found: %s' % match
