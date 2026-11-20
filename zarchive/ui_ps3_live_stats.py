"""Optional live PS3 temperature display in the console workspace."""
from datetime import datetime

from PySide6.QtCore import QTimer, QUrl
from PySide6.QtNetwork import QNetworkAccessManager, QNetworkProxy, QNetworkReply, QNetworkRequest
from PySide6.QtWidgets import QDialog, QFormLayout, QLabel, QLineEdit, QPushButton, QVBoxLayout

from .ps3_live_stats import MAX_RESPONSE, parse_temperatures, temperature_url


class LiveTemperatures(QDialog):
    def __init__(self, host='', parent=None):
        super().__init__(parent)
        self.setWindowTitle('PS3 Live Temperatures')
        layout = QVBoxLayout(self)
        detail = QLabel('Requires webMAN MOD’s web server on the PS3. '
                        'Save Archive reads CELL and RSX temperatures every 5 seconds.')
        detail.setWordWrap(True)
        layout.addWidget(detail)
        form = QFormLayout()
        layout.addLayout(form)
        self.host = QLineEdit(host)
        self.host.setPlaceholderText('192.168.1.50')
        self.cell = QLabel('—')
        self.rsx = QLabel('—')
        form.addRow('PS3 IP address', self.host)
        form.addRow('CELL', self.cell)
        form.addRow('RSX', self.rsx)
        self.status = QLabel('Ready to connect.')
        self.status.setWordWrap(True)
        layout.addWidget(self.status)
        self.toggle = QPushButton('Start monitoring')
        self.toggle.clicked.connect(self.toggle_monitor)
        layout.addWidget(self.toggle)
        close = QPushButton('Close')
        close.clicked.connect(self.reject)
        layout.addWidget(close)

        self.network = QNetworkAccessManager(self)
        self.network.setProxy(QNetworkProxy(QNetworkProxy.ProxyType.NoProxy))
        self.timer = QTimer(self, interval=5000)
        self.timer.timeout.connect(self.poll)
        self.deadline = QTimer(self, interval=3500, singleShot=True)
        self.deadline.timeout.connect(self.cancel_request)
        self.reply = None

    def toggle_monitor(self):
        if self.timer.isActive():
            self.stop()
            self.clear_readings('Monitoring stopped.')
            return
        try:
            self.url = QUrl(temperature_url(self.host.text().strip()))
        except ValueError:
            self.clear_readings('Enter your PS3’s private LAN IPv4 address.')
            return
        self.host.setEnabled(False)
        self.toggle.setText('Stop monitoring')
        self.clear_readings('Connecting to webMAN MOD…')
        self.timer.start()
        self.poll()

    def poll(self):
        if self.reply is not None:
            return
        request = QNetworkRequest(self.url)
        request.setAttribute(QNetworkRequest.Attribute.RedirectPolicyAttribute,
                             QNetworkRequest.RedirectPolicy.ManualRedirectPolicy)
        request.setAttribute(QNetworkRequest.Attribute.CacheLoadControlAttribute,
                             QNetworkRequest.CacheLoadControl.AlwaysNetwork)
        self.reply = self.network.get(request)
        self.reply.setReadBufferSize(MAX_RESPONSE + 1)
        self.reply.readyRead.connect(self.check_size)
        self.reply.finished.connect(self.response_finished)
        self.deadline.start()

    def check_size(self):
        if self.reply is not None and self.reply.bytesAvailable() > MAX_RESPONSE:
            self.cancel_request('webMAN MOD sent an unexpectedly large response.')

    def cancel_request(self, message='No response from webMAN MOD. Check the address and web server.'):
        reply, self.reply = self.reply, None
        self.deadline.stop()
        if reply is not None:
            reply.abort()
            reply.deleteLater()
        self.clear_readings(message)

    def response_finished(self):
        reply, self.reply = self.reply, None
        self.deadline.stop()
        if reply is None:
            return
        try:
            if (reply.error() != QNetworkReply.NetworkError.NoError
                    or reply.attribute(QNetworkRequest.Attribute.HttpStatusCodeAttribute) != 200):
                raise ValueError('Cannot read webMAN MOD temperatures. Check the PS3 IP and web server.')
            if reply.bytesAvailable() > MAX_RESPONSE:
                raise ValueError('webMAN MOD sent an unexpectedly large response.')
            cell, rsx = parse_temperatures(bytes(reply.readAll()))
        except ValueError as error:
            self.clear_readings(str(error))
        else:
            self.cell.setText(f'{cell} °C')
            self.rsx.setText(f'{rsx} °C')
            self.status.setText(f'Updated {datetime.now():%H:%M:%S}')
        finally:
            reply.deleteLater()

    def clear_readings(self, message):
        self.cell.setText('—')
        self.rsx.setText('—')
        self.status.setText(message)

    def stop(self):
        self.timer.stop()
        self.cancel_request('Monitoring stopped.')
        self.toggle.setText('Start monitoring')
        self.host.setEnabled(True)

    def done(self, result):
        self.stop()
        super().done(result)
