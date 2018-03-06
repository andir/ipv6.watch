FROM python:3.6-stretch

ADD requirements.txt templates run.py /code/
WORKDIR /code
RUN pip install -r requirements.txt
ADD dist /code/dist
ADD conf.yaml /code/
EXPOSE 8080
CMD python run.py serve
