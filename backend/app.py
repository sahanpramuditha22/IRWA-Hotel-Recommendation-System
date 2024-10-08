import pickle
import pandas as pd
import numpy as np
from flask import Flask, request, jsonify
from sklearn.metrics.pairwise import cosine_similarity
import firebase_admin
from firebase_admin import credentials, db
from flask_cors import CORS
from hotel_search import requirementbased

app = Flask(__name__)
CORS(app,resources={r"/*": {"origins": "*"}})



with open('userbasedcollabarete2.pkl', 'rb') as file:
    hotel_df = pickle.load(file)
    
with open('hotels.pkl', 'rb') as file:
    hotel_df2 = pickle.load(file)    

user_hotel_matrix = hotel_df.pivot_table(index='user_id', columns='hotelname', values='starrating_x', fill_value=0)
user_hotel_matrix.index = user_hotel_matrix.index.astype(str)  


class HotelRecSys:
    def __init__(self, user_hotel_matrix):
        self.user_hotel_matrix = user_hotel_matrix
        self.similarity_matrix = None

    def calc_user_user_similarity(self):
        self.similarity_matrix = cosine_similarity(self.user_hotel_matrix)
        np.fill_diagonal(self.similarity_matrix, 0)

    def recommend_hotels(self, user_id, k=8):
        if user_id not in self.user_hotel_matrix.index:
            return []
        
        user_idx = self.user_hotel_matrix.index.get_loc(user_id)
        similar_users = np.argsort(self.similarity_matrix[user_idx])[::-1]
        top_similar_users = similar_users[:k]

        user_ratings = self.user_hotel_matrix.iloc[user_idx]
        hotel_scores = np.zeros(self.user_hotel_matrix.shape[1])

        for sim_user_idx in top_similar_users:
            sim_user_ratings = self.user_hotel_matrix.iloc[sim_user_idx]
            hotel_scores += sim_user_ratings

        unrated_hotels = user_ratings[user_ratings == 0].index
        recommendations = [(hotel, score) for hotel, score in zip(self.user_hotel_matrix.columns, hotel_scores) if hotel in unrated_hotels]
        recommendations = sorted(recommendations, key=lambda x: x[1], reverse=True)

        return recommendations[:k]
    
    def get_most_popular_hotels(self, top_n=8):
        
        ratings_count = (self.user_hotel_matrix > 0).sum().sort_values(ascending=False)
        
        popular_hotels = ratings_count.head(top_n).index.tolist()
        return popular_hotels

rec_sys = HotelRecSys(user_hotel_matrix)
rec_sys.calc_user_user_similarity()






@app.route('/login', methods=['POST'])
def login():
    data = request.json
    user_id = data.get('user_id')

    if user_id and verify_user_id(user_id):
        return jsonify({'status': 'success', 'message': 'Login successful', 'user_id': user_id}), 200
    return jsonify({'status': 'error', 'message': 'Invalid User ID'}), 400


@app.route('/recommend', methods=['POST'])
def recommend():
    data = request.json
    user_id = data.get('user_id')
    
    if user_id in user_hotel_matrix.index:
        recommendations = rec_sys.recommend_hotels(user_id)
        return jsonify({'status': 'success', 'recommendations': recommendations}), 200
    return jsonify({'status': 'error', 'message': 'User not found in dataset'}), 400


@app.route('/popular', methods=['GET'])
def popular():
    try:
        top_n = int(request.args.get('top', 8))  
    except ValueError:
        top_n = 10  

    popular_hotels = rec_sys.get_most_popular_hotels(top_n)
    # Optionally, include additional data like number of ratings
    ratings_count = (user_hotel_matrix > 0).sum().loc[popular_hotels].to_dict()
    popular_hotels_with_counts = [{"hotel": hotel, "ratings_count": count} for hotel, count in ratings_count.items()]
    
    return jsonify({'status': 'success', 'popular_hotels': popular_hotels_with_counts}), 200





import logging

logging.basicConfig(level=logging.DEBUG)

@app.route('/search_hotels', methods=['POST'])
def search_hotels():
    data = request.json
    city = data.get('city', '').lower()
    number = data.get('number', 1)
    features = data.get('features', '').lower()
    
    try:
        number = int(number)
    except ValueError:
        number = 1
        logging.warning(f"Invalid number provided: {data.get('number')}. Defaulting to 1.")
    
    logging.debug(f"Searching hotels in {city} for {number} guests with features: {features}")
    
    results = requirementbased(city, number, features)
    logging.debug(f"Found {len(results)} matching hotels.")
    
    return jsonify(results)


def get_countries_and_cities():
    countries = hotel_df2['country'].unique().tolist()
    cities = hotel_df2[['country', 'city']].drop_duplicates().to_dict(orient='records')
    return countries, cities

# Get hotel recommendations based on country and city
def recommend_hotels(country, city):
    filtered_hotels = hotel_df2[(hotel_df2['country'] == country) & (hotel_df2['city'] == city)]
    if filtered_hotels.empty:
        return []
    recommended_hotels = filtered_hotels[['hotelname', 'roomtype']].to_dict(orient='records')
    return recommended_hotels

@app.route('/get_countries_and_cities', methods=['GET'])
def countries_and_cities():
    try:
        countries, cities = get_countries_and_cities()
        return jsonify({'status': 'success', 'countries': countries, 'cities': cities})
    except Exception as e:
        return jsonify({'status': 'error', 'message': str(e)})

@app.route('/recommend_new', methods=['POST'])
def recommend_new():
    try:
        data = request.json
        country = data.get('country')
        city = data.get('city')
        
        if not country or not city:
            return jsonify({'status': 'error', 'message': 'Country and City are required'})

        recommendations = recommend_hotels(country, city)
        if recommendations:
            return jsonify(recommendations)
        else:
            return jsonify({'status': 'error', 'message': 'No hotels found for the selected location'})
    except Exception as e:
        return jsonify({'status': 'error', 'message': str(e)})



if __name__ == '__main__':
    app.run(debug=True)
