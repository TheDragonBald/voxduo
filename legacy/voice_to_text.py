import tkinter as tk
from tkinter import scrolledtext
import sounddevice as sd
import soundfile as sf
import whisper
import pyperclip
import numpy as np
import threading
import os

class VoiceToTextApp:
    def __init__(self, root):
        self.root = root
        self.root.title("Rumor n' Gossip - Voice to Text")
        self.root.geometry("600x400")
        
        # Переменные
        self.is_recording = False
        self.audio_data = []
        self.sample_rate = 16000
        
        # Загрузка модели Whisper (делаем один раз)
        self.status_label = tk.Label(root, text="Загрузка модели Whisper...", font=("Arial", 10))
        self.status_label.pack(pady=10)
        self.root.update()
        
        self.model = whisper.load_model("small")
        self.status_label.config(text="Готов к работе!")
        
        # Кнопки
        self.record_button = tk.Button(root, text="🎤 Записать", command=self.toggle_recording, 
                                       bg="#4CAF50", fg="white", font=("Arial", 14), width=15, height=2)
        self.record_button.pack(pady=10)
        
        # Текстовое поле
        self.text_area = scrolledtext.ScrolledText(root, wrap=tk.WORD, font=("Arial", 11), height=12)
        self.text_area.pack(padx=10, pady=10, fill=tk.BOTH, expand=True)
        
        # Кнопка копирования
        self.copy_button = tk.Button(root, text="📋 Копировать", command=self.copy_text, 
                                     font=("Arial", 12), width=15)
        self.copy_button.pack(pady=5)
    
    def toggle_recording(self):
        if not self.is_recording:
            self.start_recording()
        else:
            self.stop_recording()
    
    def start_recording(self):
        self.is_recording = True
        self.audio_data = []
        self.record_button.config(text="⏹️ Стоп", bg="#f44336")
        self.status_label.config(text="Идет запись...")
        
        # Запись в отдельном потоке
        def record():
            with sd.InputStream(samplerate=self.sample_rate, channels=1, callback=self.audio_callback):
                while self.is_recording:
                    sd.sleep(100)
        
        threading.Thread(target=record, daemon=True).start()
    
    def audio_callback(self, indata, frames, time, status):
        if self.is_recording:
            self.audio_data.append(indata.copy())
    
    def stop_recording(self):
        self.is_recording = False
        self.record_button.config(text="🎤 Записать", bg="#4CAF50")
        self.status_label.config(text="Обработка...")
        
        # Транскрибация в отдельном потоке
        threading.Thread(target=self.transcribe, daemon=True).start()
    
    def transcribe(self):
        try:
            # Сохранение аудио во временный файл
            import os
            audio_array = np.concatenate(self.audio_data, axis=0)
            
            # Полный путь к временному файлу
            temp_file = os.path.join(os.path.dirname(__file__), "temp_audio.wav")
            
            sf.write(temp_file, audio_array, self.sample_rate)
            
            # Транскрибация
            result = self.model.transcribe(temp_file, language="ru", fp16=False)
            text = result["text"]
            
            # Удаляем временный файл
            if os.path.exists(temp_file):
                os.remove(temp_file)
            
            # Вывод результата
            self.text_area.delete(1.0, tk.END)
            self.text_area.insert(tk.END, text)
            self.status_label.config(text="Готово!")
            
        except Exception as e:
            self.status_label.config(text=f"Ошибка: {str(e)}")
            print(f"Полная ошибка: {e}")  # Для отладки
    
    def copy_text(self):
        text = self.text_area.get(1.0, tk.END).strip()
        if text:
            pyperclip.copy(text)
            self.status_label.config(text="Текст скопирован!")

if __name__ == "__main__":
    root = tk.Tk()
    app = VoiceToTextApp(root)
    root.mainloop()