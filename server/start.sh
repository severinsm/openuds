#! /bin/bash

# Start the first process
python ./src/manage.py runserver '0.0.0.0:8000' &
python ./src/manage.py taskManager --start &