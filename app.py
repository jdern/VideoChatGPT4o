import os
from pathlib import Path
from openai import OpenAI
import datauri 
import openaikey
import ffmpeg
from base64 import b64decode

# Step 1 : Split audio and video frames
def split_video(video_file, framesnumber = 1):
    # If not a file but base64 video, convert to a file
    if video_file[:5] == 'data:':
        str = video_file[22:]
        video_file = temppath+"/video.mp4"
        with open(video_file, 'wb') as f:
            f.write(b64decode(str))
    
    # Extract frames from the video
    process = (
        ffmpeg
        .input(video_file)
        .output(temppath+'/frame_%d.png', vframes=framesnumber)
        .overwrite_output()
        .run()
    )

    #extract audio from the video
    audio_uri = temppath+'/audio.mp3'
    process = (
        ffmpeg
        .input(video_file)
        .output(audio_uri)
        .overwrite_output()
        .run()
    )

    video_uris = [ datauri.DataURI.from_file(temppath+'/frame_%d.png'%d) for d in range(1, framesnumber+1)]
    return audio_uri, video_uris

# Step 2 : transform the audio from video to text
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

# Step 3 : Send audio text and frames to ChatGPT4o for analysis and get its answer 
def GetAnswerTextChatPPT4o(user_prompt, image_uris):
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

# Step 4 : transform the text answer of ChatGPT4o to audio with OpenAI TTS API
def Text2Audio(response_text): 
    audio = client.audio.speech.create(
        model           = "tts-1", 
        voice           = "nova",
        input           = response_text, 
        response_format = "mp3"
    )
    response_audio_uri = temppath+"/output.mp3"
    audio.stream_to_file(response_audio_uri) 
    return response_audio_uri

# Not Used in this demo : all in one process from a video snippet, return audio file
def AskChatGPT4o(video_file): 
    audio_uri, image_uris = split_video(video_file)
    user_prompt = Transcription(audio_uri)
    response_text = GetAnswerTextChatPPT4o(user_prompt, image_uris)
    response_audio_uri = Text2Audio(response_text)
    return response_audio_uri

# Web interface for quick prototyping using Shiny framework
from shiny.express import input, render, ui
from shinymedia import input_video_clip, audio_spinner 

# Connect to OpenAI
client = OpenAI()

# Use a temp folder in the parent directory (else it perturbate Shiny in case of changes)
temppath = os.path.dirname(os.path.dirname(__file__))+"/TempDir"

# Widget to record and display video camera and sound
input_video_clip("video", style="max-width: 600px;", class_="mx-auto py-3") 

# Will be executed when a video has been recorded
@render.express
def video_size():
    # A video exist
    if input.video() is not None:
        # Create a progress information as the whole process may be a little bit long
        with ui.Progress() as p:
            # Step 1: Split
            p.set(message="Processing media...")
            audio_uri, image_uris = split_video(input.video())
            # Step 2: Recognize
            p.set(message="Processing audio recognition...")
            user_prompt = Transcription(audio_uri)
            # Display recognized text
            ui.p("Vous avez dit : " + user_prompt, placeholder=True)
            # Send frames and recognized text to ChatGPT4o 
            p.set(message="Processing answer...")
            response_text = GetAnswerTextChatPPT4o(user_prompt, image_uris)
            # display the answer
            ui.p("La réponse est : " + response_text, placeholder=True)
            # Convert the answer to audio
            p.set(message="Processing audio generation...")
            audio_uri = Text2Audio(response_text)
        # Speak the audio
        audio_spinner(src=audio_uri)
        # Finished, next recording please
        return