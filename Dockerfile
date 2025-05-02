FROM python:3.11

RUN apt-get update && \
    apt-get upgrade -y && \
    apt-get install -y vim \
                       git \
                       curl \
                       wget 

COPY requirements.txt /home
RUN pip install --upgrade pip &&\
    pip install -r /home/requirements.txt &&\
    rm /home/requirements.txt
    
WORKDIR /home/work
CMD [ "/bin/bash" ]
