import streamlit as st
import pandas as pd
import time
import os
import math
import re
import random
import requests

# 화면 설정
st.set_page_config(page_title="AI 맛집 랭킹 (Cloud)", page_icon="☁️", layout="wide")

from streamlit_folium import st_folium
import folium
from selenium import webdriver
from selenium.webdriver.common.by import By
from selenium.webdriver.common.keys import Keys
from selenium.webdriver.chrome.options import Options
from selenium.webdriver.chrome.service import Service
from webdriver_manager.chrome import ChromeDriverManager
from selenium.webdriver.support.ui import WebDriverWait
from selenium.webdriver.support import expected_conditions as EC

# ==========================================
# 1. 도구 설정
# ==========================================

def get_lat_lon(address):
    VWORLD_API_KEY = "05B55DB4-5776-37FB-B555-BE393DE47184" 
    try:
        clean_addr = address.split("(")[0].strip()
        url = "http://api.vworld.kr/req/address?"
        params = {
            "service": "address", "request": "getcoord", "version": "2.0",
            "crs": "epsg:4326", "address": clean_addr, "refine": "true",
            "simple": "false", "format": "json", "type": "ROAD", "key": VWORLD_API_KEY
        }
        response = requests.get(url, params=params, timeout=3)
        data = response.json()
        if data['response']['status'] == 'OK':
            return float(data['response']['result']['point']['y']), float(data['response']['result']['point']['x'])
        else:
            params['type'] = 'PARCEL'
            response = requests.get(url, params=params, timeout=3)
            data = response.json()
            if data['response']['status'] == 'OK':
                return float(data['response']['result']['point']['y']), float(data['response']['result']['point']['x'])
    except: return None, None
    return None, None

class RecommendationEngine:
    def __init__(self):
        self.weights = {"rating": 2.0, "match": 1.0}

    def calculate_score(self, row):
