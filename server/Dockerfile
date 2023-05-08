# base image  
FROM python:3.10
# setup environment variable  
ENV DockerHOME=/home/uds/server  

# set work directory  
RUN mkdir -p $DockerHOME  

# where your code lives  
WORKDIR $DockerHOME  

# set environment variables  
ENV PYTHONDONTWRITEBYTECODE 1
ENV PYTHONUNBUFFERED 1  

# install dependencies  
RUN pip install --upgrade pip  
RUN apt update && apt install libsasl2-dev python-dev libldap2-dev libssl-dev -y

# copy whole project to your docker home directory. 
COPY . $DockerHOME  
# run this command to install all dependencies  
RUN pip install -r requirements.txt  
# port where the Django app runs  
EXPOSE 8000
# start server  
RUN chmod +x start.sh
CMD ["./start.sh"]