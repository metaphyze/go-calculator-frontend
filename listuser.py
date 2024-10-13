from pymongo import MongoClient

client = MongoClient('44.203.196.77', 27017)
db = client['users']
users = db.users.find()
for user in users:
    print(user)

user_data = db.users.find({"name": 'admin'})
for user in user_data:
    print(user)