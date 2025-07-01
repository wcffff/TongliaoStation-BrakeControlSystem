from PyQt5.QtCore import QUrl, QObject, QTimer
from PyQt5.QtMultimedia import QMediaPlayer, QMediaContent
import os, sys

class VoiceAlertPlayer(QObject):
    def __init__(self):
        super().__init__()
        self.media_folder = self.get_media_folder()
        self.player = QMediaPlayer()
        self.queue = []
        self.is_playing = False

        self.player.mediaStatusChanged.connect(self._handle_media_status)

    def get_media_folder(self):
        if getattr(sys, 'frozen', False):
            # exe 运行
            base_dir = os.path.dirname(sys.executable)
        else:
            # 源码运行
            base_dir = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
        return os.path.join(base_dir, "data", "media")

    # def add_alert_to_queue(self, filename):
    #     filepath = os.path.join(self.media_folder, f"{filename}.mp3")
    #     print(f"[VoiceAlert] 尝试播放文件路径: {filepath}")
    #     if os.path.exists(filepath):
    #         self.queue.append(filepath)
    #         self._try_play_next()
    #     else:
    #         print(f"[VoiceAlert] 文件不存在: {filepath}")

    def add_alert_to_queue(self, filename):
        filepath = os.path.join(self.media_folder, f"{filename}.mp3")
        print(f"[VoiceAlert] 尝试播放文件路径: {filepath}")

        if not os.path.exists(filepath):
            print(f"[VoiceAlert] 文件不存在: {filepath}")
            return

        # 如果正在播放这个，或者队列里已经有，就不重复入队
        if (self.is_playing and self.player.media().canonicalUrl().toLocalFile() == filepath) \
                or (filepath in self.queue):
            print(f"[VoiceAlert] 已在播放或队列中，跳过重复入队: {filepath}")
            return

        self.queue.append(filepath)
        self._try_play_next()

    def _try_play_next(self):
        if self.is_playing or not self.queue:
            return

        next_file = self.queue.pop(0)
        media = QMediaContent(QUrl.fromLocalFile(next_file))
        self.player.setMedia(media)
        self.player.play()
        self.is_playing = True

    def _handle_media_status(self, status):
        if status == QMediaPlayer.EndOfMedia:
            self.is_playing = False
            self._try_play_next()
