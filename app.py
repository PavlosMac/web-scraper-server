from typing import Dict, List, Any

from flask import Flask, request
from flask_sqlalchemy import SQLAlchemy
from flask_migrate import Migrate
import requests
import operator
from stops import stops
import os
import re
import nltk
from collections import Counter
from bs4 import BeautifulSoup
from rq import Queue
from rq.job import Job
from worker import conn
from flask import jsonify
from sqlalchemy.exc import SQLAlchemyError

app = Flask(__name__)
app.config.from_object(os.environ['APP_SETTINGS'])
app.config['SQLALCHEMY_TRACK_MODIFICATIONS'] = True
db = SQLAlchemy(app)
migrate = Migrate(app, db)
q = Queue(connection=conn)

from models import *

@app.route("/results/<job_key>", methods=['GET'])
def get_results(job_key):
    job = Job.fetch(job_key, connection=conn)

    if job.is_finished:
        result = Result.query.filter_by(id=job.result).first()
        results = sorted(
            result.result_no_stop_words.items(),
            key=operator.itemgetter(1),
            reverse=True
        )[:500]

        if request.args.get("keywords"):
            create_list = request.args.get("keywords").split(',')
            check_matched = get_matched_results(create_list, results)
            if len(check_matched) > 0:
                results = check_matched
            else:
                return jsonify({"status":"no match"})

        dic_list = get_list_of_dict(('word', 'count'), results)
        return jsonify(dic_list)
    else:
        return jsonify({"status":"pending"}), 202

@app.route('/start', methods=['POST'])
def get_counts():
    data = request.get_json()
    url = data["url"]

    if not 'https://' in url[:7]:
        if not 'www.' in url[:4]:
            url = 'www.' + url
        url = 'https://' + url

    job = q.enqueue_call(
        func=count_and_save_words, args=(url,), result_ttl=5000
    )
    return jsonify({"jobId": job.get_id()})

def count_and_save_words(url):
    errors = []
    try:
        r = requests.get(url)
    except ConnectionError:
        errors.append("Unable to get URL. Please make sure it's valid and try again.")
        print('ERRORS =12222= ' + str(errors))

    if errors:
        return jsonify({"errors": errors}), 202

    raw = BeautifulSoup(r.text, features="html.parser").get_text()
    nltk.data.path.append('./nltk_data/')  # set the path
    tokens = nltk.word_tokenize(raw)
    text = nltk.Text(tokens)
    nonPunct = re.compile('.*[A-Za-z].*')
    raw_words = [w for w in text if nonPunct.match(w)]
    raw_word_count = Counter(raw_words)
    no_stop_words = [w for w in raw_words if w.lower() not in stops]
    no_stop_words_count = Counter(no_stop_words)

    try:
        result = Result(
            url=url,
            result_all=raw_word_count,
            result_no_stop_words=no_stop_words_count
        )
        db.session.add(result)
        db.session.commit()
        return result.id
    except SQLAlchemyError as e:
        errors.append("Unable to add item to database.")
        return {"error": errors}

def get_list_of_dict(keyz, list_of_tuples):
    list_of_dict: List[Dict[String, int]] = [dict(zip(keyz, values)) for values in list_of_tuples]
    return list_of_dict

def get_matched_results(input, scraped):
    list_results = [v.lower() for v in input]
    matched = {}
    for x, y in scraped:
        if x.lower() in list_results:
            if matched.get(x.lower()):
                matched[x.lower()] += y
            else:
                matched[x.lower()] = y

    return [(k, v) for k, v in matched.items()]

if __name__ == '__main__':
    app.run()
