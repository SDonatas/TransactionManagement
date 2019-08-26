#Databases

#Setup of merchants and credit cards is within sqlite
setup.db // Automatically created if non-existant

#Transaction data is within sqlite 
data.db // Automatically created if non-existant 


#Installation

#Setup virtual environment (or alternatively used operating system's python libraries if existant)
virtualenv -p python3 venv

#Activate
source venv/bin/activate

#find requirements file and install
pip install -r requirements.txt


#Host the app on heruko, locally with apache or other web hosting service
#Or Run locally (non production, will work for single user, but will handle poorly with multi-users)
python3 app.py
