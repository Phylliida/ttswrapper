import grequests
from flask import Flask, request, jsonify, url_for, send_file
app = Flask(__name__)

from gtts import gTTS
import requests
import json
import os
from pathlib import Path
import re
import io
import uuid
import urllib.parse
from apscheduler.schedulers.background import BackgroundScheduler
from apscheduler.triggers.interval import IntervalTrigger
import arrow
import atexit
from num2words import num2words

# converts numbers into spoken words
def convertNumbers(text):
    text = re.sub(' +', ' ', re.sub('([0-9,]+)', r' \1 ', text))
    print(text)
    words = text.split(" ")
    print(words)
    resWords = []
    for word in words:
        wordJustNumbers = re.sub('[^0-9]', '', word)
        if len(wordJustNumbers) > 0:
            try:
                resWords.append(num2words(wordJustNumbers))
            except:
                resWords.append(word)
        else:
            resWords.append(word)
    return re.sub(' +', ' ', " ".join(resWords).strip()).strip()

from pydub import AudioSegment

# from https://stackoverflow.com/questions/12485666/python-deleting-all-files-in-a-folder-older-than-x-days
# deletes all data files more than 4 hours old
def cleanUpFiles():
    criticalTime = arrow.now().shift(hours=-2)
    print("running cleanup")
    filesToRemove = []
    for item in Path("data").glob('*'):
        if item.is_file():
            itemTime = arrow.get(item.stat().st_mtime)
            if itemTime < criticalTime:
                filesToRemove.append(str(item))
    for fileToRemove in filesToRemove:
        print("removing: " + str(fileToRemove))
        os.remove(fileToRemove)

        
        
GTTS_CACHE = {}

PONY_URL = 'https://api.15.ai/app/getAudioFile5'
PONY_WAV_URL = 'https://cdn.15.ai/audio/'

PONY_HEADERS  = {
      'authority': 'api.15.ai',
      'access-control-allow-origin': '*',
      'accept': 'application/json, text/plain, */*',
      'sec-ch-ua-mobile': '?0',
      'user-agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/94.0.4606.61 Safari/537.36',
      'sec-ch-ua': '"Chromium";v="94", "Google Chrome";v="94", ";Not A Brand";v="99"',
      'sec-ch-ua-platform': '"Windows"',
      'content-type': 'application/json;charset=UTF-8',
      'origin': 'https://15.ai',
      'sec-fetch-site': 'same-site',
      'sec-fetch-mode': 'cors',
      'sec-fetch-dest': 'empty',
      'referer': 'https://15.ai/',
      'accept-language': 'en-US,en;q=0.9',
  }
  

PONY_WAV_HEADERS = {
      'authority': 'cdn.15.ai',
      'sec-ch-ua': '"Chromium";v="94", "Google Chrome";v="94", ";Not A Brand";v="99"',
      'sec-ch-ua-mobile': '?0',
      'user-agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/94.0.4606.61 Safari/537.36',
      'sec-ch-ua-platform': '"Windows"',
      'accept': '*/*',
      'origin': 'https://15.ai',
      'sec-fetch-site': 'same-site',
      'sec-fetch-mode': 'cors',
      'sec-fetch-dest': 'empty',
      'referer': 'https://15.ai/',
      'accept-language': 'en-US,en;q=0.9',
  }  


def getPonyData(text, character):
  data = '{"text":"' + text + '","character":"' + character + '","emotion":"Contextual"}'
  return data
  
  
def getWavUrl(response):
    return PONY_WAV_URL + json.loads(response.text)['wavNames'][0]
    
    
def callPonyAsync(request, texts, character):
    rs = (grequests.post(PONY_URL, headers=PONY_HEADERS, data=getPonyData(text, character)) for text in texts)
    
    results = grequests.map(rs)
    wavURLS = [getWavUrl(response) for response in results]
    
    rs = (grequests.get(wavURL) for wavURL in wavURLS)
    wavFileRequests = grequests.map(rs)
    audioSegments = []
    for wavFileRequest in wavFileRequests:
        wavFileRequest.raise_for_status()
        with io.BytesIO() as f:
            for chunk in wavFileRequest.iter_content(chunk_size=8192):
                f.write(chunk)
            f.seek(0)
            audioSegments.append(AudioSegment.from_file(f))
    resSegment = audioSegments[0]
    for audioSegment in audioSegments[1:]:
        resSegment = resSegment + audioSegment
    
    Path("data").mkdir(parents=True, exist_ok=True)
    outURL = "data/15ai" + str(uuid.uuid4()) + ".ogg"
    resSegment.export(outURL, format='ogg')
    return request.host_url + outURL
        
def sanitizeText(text):
    text = text.replace("\n", ". ").replace("\t", " ") # clean spaces
    text = re.sub(r"[^A-Za-z0-9'\-\.\,\?\!\| \{\}\[\]]", "", text) # remove forbidden characters
    text = text.replace("|", "vertical bar")
    text = re.sub(' +', ' ', text) # remove duplicate spaces
    text = re.sub(r' ([\.\,\?\!])', r'\1', text) # "hi ." -> "hi."
    return text
    
def getCutOffPoint(text):
    return max([text.rfind(cutoff) for cutoff in [' ', ',', '.', '!', '?', '-']])
    
import time
global allChunks
allChunks = []
def callRateLimit(chunks, voice):
    global allChunks
    allChunks = []
    for i, chunk in enumerate(chunks):
        time.sleep(1)
        wavFile = callPonySingle(chunk, voice)
        allChunks.append(wavFile)
        print(i, len(chunks))
        
def mergeRateLimitOutputs():
    rs = (grequests.get(wavURL) for wavURL in wavURLS)
    wavFileRequests = grequests.map(rs)
    audioSegments = []
    for wavFileRequest in wavFileRequests:
        wavFileRequest.raise_for_status()
        with io.BytesIO() as f:
            for chunk in wavFileRequest.iter_content(chunk_size=8192):
                f.write(chunk)
            f.seek(0)
            audioSegments.append(AudioSegment.from_file(f))
    resSegment = audioSegments[0]
    for audioSegment in audioSegments[1:]:
        resSegment = resSegment + audioSegment
    
    resSegment.export("antimeme.ogg", format='ogg')
        
def splitIntoChunks(text, chunkSize):
    if len(text) < chunkSize:
        return [text]
    curText = text
    chunks = []
    while len(curText) > 0:
        needToParse = curText[:chunkSize]
        cutOffPoint = getCutOffPoint(needToParse)
        if cutOffPoint <= 0:
            cutOffPoint = chunkSize
        chunks.append(curText[:cutOffPoint])
        curText = curText[cutOffPoint:].strip()
    return chunks   

def callPony(request, text, character):
    text = sanitizeText(text)
    text = convertNumbers(text)
    if len(text) == 0: raise Exception("Empty string")
    chunks = splitIntoChunks(text, 200) # max request size is 200
    print(chunks)
    if len(chunks) == 1:
        return callPonySingle(chunks[0], character)
    else:
        return callPonyAsync(request, chunks[:3], character) # don't do more than 3 chunks so we don't spam
        
# k guise
# calls 15.ai model
def callPonySingle(text, character):

  headers = {
      'authority': 'api.15.ai',
      'access-control-allow-origin': '*',
      'accept': 'application/json, text/plain, */*',
      'sec-ch-ua-mobile': '?0',
      'user-agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/94.0.4606.61 Safari/537.36',
      'sec-ch-ua': '"Chromium";v="94", "Google Chrome";v="94", ";Not A Brand";v="99"',
      'sec-ch-ua-platform': '"Windows"',
      'content-type': 'application/json;charset=UTF-8',
      'origin': 'https://15.ai',
      'sec-fetch-site': 'same-site',
      'sec-fetch-mode': 'cors',
      'sec-fetch-dest': 'empty',
      'referer': 'https://15.ai/',
      'accept-language': 'en-US,en;q=0.9',
  }

  data = '{"text":"' + text + '","character":"' + character + '","emotion":"Contextual"}'
  
  
  response = requests.post(PONY_URL, headers=PONY_HEADERS, data=data)
  
  wavName = json.loads(response.text)['wavNames'][0] # like nQJFDSJJKAFS.wav
  url = 'https://cdn.15.ai/audio/' + wavName
  return url
  '''
  
  with requests.get(url, headers=headers, stream=True) as r:
      r.raise_for_status()
      with open(wavName, 'wb') as f:
          for chunk in r.iter_content(chunk_size=8192): 
              # If you have chunk encoded response uncomment if
              # and set chunk_size parameter to None.
              #if chunk: 
              f.write(chunk)
  return wavName
  '''
  
  
@app.route('/data/<path:filename>', methods=['GET', 'POST'])
def getData(filename):
    Path("data").mkdir(parents=True, exist_ok=True)
    return send_file('data/' + filename)

def getGTTSFileName(text):
    if text in GTTS_CACHE:
        filename = GTTS_CACHE[text]
    else:
        filename = 'gtts-' + str(uuid.uuid4())
        GTTS_CACHE[text] = filename
    return filename
        
@app.route('/gtts', methods=['GET', 'POST'])
def get_gtts2():
    text = ""
    try:
        Path("data").mkdir(parents=True, exist_ok=True)
        if request.method == 'GET':
            text = request.args.get('text', None)
        elif request.method == 'POST':
            text = request.form.get('text', None)
        filename = getGTTSFileName(text)
        outfilemp3 = "data/" + filename + ".mp3"
        outfileogg = "data/" + filename + ".ogg"
        if not os.path.isfile(outfileogg):
            tts = gTTS(text=text)
            tts.save(outfilemp3)
            sound = AudioSegment.from_mp3(outfilemp3)
            sound.export(outfileogg, format='ogg')
        return "Success" + "\n" + str(request.host_url) + outfileogg + "\n" + text
    except Exception as e:
        return "Error" + "\n" + "\n" + text
        
@app.route('/15ai', methods=['GET', 'POST'])
def get_15ai2():
    text = ""
    try:
        if request.method == 'GET':
            char = request.args.get("character", None)
            text = request.args.get('text', None)
        elif request.method == 'POST':
            char = request.form.get("character", None)
            text = request.form.get('text', None)
        filename = callPony(request, text, char)
        return "Success" + "\n" + filename + "\n" + text
    except Exception as e:
        return "Error" + "\n" + "\n" + text
    
    
    
if __name__ == '__main__':

    scheduler = BackgroundScheduler()
    scheduler.add_job(cleanUpFiles, IntervalTrigger(seconds=60*60*3), id="filecleanup")
    scheduler.start()
    
    
    def cleanupScheduler():
        scheduler.shutdown()
        
    cleanUpFiles()

    # Shut down the scheduler when exiting the app
    atexit.register(lambda: scheduler.shutdown())
    # Threaded option to enable multiple instances for multiple user access support
    app.run(threaded=True, port=5000)
