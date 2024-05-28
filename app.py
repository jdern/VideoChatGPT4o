import os
from pathlib import Path
from openai import OpenAI
import datauri 
import openaikey
import ffmpeg
from base64 import b64decode


def split_video(video_file, framesnumber = 1):
    if video_file[:5] == 'data:':
        str = video_file[22:]
        video_file = temppath+"/video.mp4"
        with open(video_file, 'wb') as f:
            f.write(b64decode(str))
    
    process = (
        ffmpeg
        .input(video_file)
        .output(temppath+'/frame_%d.png', vframes=framesnumber)
        .overwrite_output()
        .run()
    )
    process = (
        ffmpeg
        .input(video_file)
        .output(temppath+'/audio.mp3')
        .overwrite_output()
        .run()
    )

    #audio_uri = datauri.DataURI.from_file(path+'/audio.mp3')
    audio_uri = temppath+'/audio.mp3'
    video_uris = [ datauri.DataURI.from_file(temppath+'/frame_%d.png'%d) for d in range(1, framesnumber+1)]
    return audio_uri, video_uris

def Transcription(audio_uri):
    transcription = client.audio.transcriptions.create(
        model = "whisper-1", 
        file = Path(audio_uri)
    )
    user_prompt = transcription.text
    if user_prompt == "":
        user_prompt = "Que vois-tu ?"
    print()
    print(user_prompt)
    return user_prompt

def GetAnswerTextChatPPT4o(user_prompt, image_uris):
    sysprompt = os.path.dirname(__file__)+'/system_prompt.txt'
    response = client.chat.completions.create(
        model="gpt-4o",
        messages=[
            {
                "role": "user",
                "content": [
                    { "type": "text", "text": user_prompt},
                    *[
                        {
                            "type": "image_url", 
                            "image_url": { "url": image_uri, "detail": "auto" },
                        }
                        for image_uri in image_uris
                    ],
                ],
            },
            {
                "role": "system", "content": 
                """Les images sont des trames d'une vidéo.
                L'utilisateur ne sait pas que la vidéo est divisée en images.
                Veillez donc à ce que votre vidéo désigne ces images par le terme 'la vidéo', et non 'les images'.
                Si l'utilisateur fait référence à "je" ou "moi" dans la saisie de texte, vous devez supposer qu'il s'agit de la personne centrale dans la vidéo. \
                L'utilisateur vous demande de prononcer la réponse.
                Veillez à ce que votre réponse prenne la forme d'une réponse orale amicale et décontractée.
                From now on, please answer me exclusively in French, even if I ask you in another language.""", 
            },
        ]
    )
    response_text = response.choices[0].message.content
    print(response_text)
    return response_text

def Text2Audio(response_text):
    # Use OpenAI's text-to-speech model to turn the generoted text into audio. 
    audio = client.audio.speech.create(
        model           = "tts-1", 
        voice           = "nova",
        input           = response_text, 
        response_format = "mp3"
    )
    response_audio_uri = temppath+"/output.mp3"
    audio.stream_to_file(response_audio_uri) 
    return response_audio_uri

def AskChatGPT4o(video_file): 
    audio_uri, image_uris = split_video(video_file)
    user_prompt = Transcription(audio_uri)
    response_text = GetAnswerTextChatPPT4o(user_prompt, image_uris)
    response_audio_uri = Text2Audio(response_text)
    return response_audio_uri

from shiny.express import input, render, ui
from shinymedia import input_video_clip, audio_spinner 


# Connect to OpenAI
client = OpenAI()
temppath = os.path.dirname(os.path.dirname(__file__))+"/TempDir"

input_video_clip("video", style="max-width: 600px;", class_="mx-auto py-3") 
#ui.input_file("video", label="Upload a video clip") 

@render.express
def video_size():
    if input.video() is not None:
        with ui.Progress() as p:
            #video_file = input.video()[0]["datapath"]
            p.set(message="Processing media...")
            audio_uri, image_uris = split_video(input.video())
            p.set(message="Processing audio recognition...")
            user_prompt = Transcription(audio_uri)
            ui.p("Vous avez dit : " + user_prompt, placeholder=True)
            p.set(message="Processing answer...")
            response_text = GetAnswerTextChatPPT4o(user_prompt, image_uris)
            ui.p("La réponse est : " + response_text, placeholder=True)
            p.set(message="Processing audio generation...")
            audio_uri = Text2Audio(response_text)
        #audio_uri = datauri.DataURI.from_file(audio_uri)
        #ui.tags.audio(src=audio, controls=True)
        audio_spinner(src=audio_uri)
        return