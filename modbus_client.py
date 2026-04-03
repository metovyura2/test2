#!/usr/bin/env python3
"""
Modbus Client GUI - Аналог Modbus Poll
Поддерживает Modbus TCP и Modbus RTU (через последовательный порт)
"""

import sys
import threading
from PyQt6.QtWidgets import (
    QApplication, QMainWindow, QWidget, QVBoxLayout, QHBoxLayout,
    QLabel, QLineEdit, QPushButton, QComboBox, QSpinBox, QTableWidget,
    QTableWidgetItem, QGroupBox, QFormLayout, QMessageBox, QTabWidget,
    QRadioButton, QButtonGroup
)
from PyQt6.QtCore import QTimer, Qt
from pymodbus.client import ModbusTcpClient, ModbusSerialClient
from pymodbus.constants import Endian
from pymodbus.payload import BinaryPayloadDecoder


class ModbusClientApp(QMainWindow):
    def __init__(self):
        super().__init__()
        self.setWindowTitle("Modbus Client - Аналог Modbus Poll")
        self.setGeometry(100, 100, 1200, 800)
        
        self.client = None
        self.timer = QTimer()
        self.timer.timeout.connect(self.poll_data)
        self.is_polling = False
        
        self.init_ui()
        
    def init_ui(self):
        central_widget = QWidget()
        self.setCentralWidget(central_widget)
        main_layout = QVBoxLayout(central_widget)
        
        # Настройки подключения
        connection_group = QGroupBox("Настройки подключения")
        connection_layout = QFormLayout()
        
        # Тип подключения
        self.tcp_radio = QRadioButton("Modbus TCP")
        self.rtu_radio = QRadioButton("Modbus RTU (Serial)")
        self.rtu_radio.setChecked(False)
        
        type_layout = QHBoxLayout()
        type_layout.addWidget(self.tcp_radio)
        type_layout.addWidget(self.rtu_radio)
        self.type_group = QButtonGroup()
        self.type_group.addButton(self.tcp_radio)
        self.type_group.addButton(self.rtu_radio)
        
        connection_layout.addRow(type_layout)
        
        # Параметры TCP
        self.host_input = QLineEdit("127.0.0.1")
        self.host_input.setPlaceholderText("IP адрес")
        connection_layout.addRow("Host:", self.host_input)
        
        self.port_input = QSpinBox()
        self.port_input.setRange(1, 65535)
        self.port_input.setValue(502)
        connection_layout.addRow("Port:", self.port_input)
        
        # Параметры RTU
        self.serial_port_input = QComboBox()
        self.serial_port_input.addItems(["/dev/ttyUSB0", "/dev/ttyS0", "COM1", "COM2"])
        self.serial_port_input.setEditable(True)
        connection_layout.addRow("Serial Port:", self.serial_port_input)
        
        self.baud_rate_input = QSpinBox()
        self.baud_rate_input.setRange(1200, 115200)
        self.baud_rate_input.setValue(9600)
        connection_layout.addRow("Baud Rate:", self.baud_rate_input)
        
        # Общие параметры
        self.slave_id_input = QSpinBox()
        self.slave_id_input.setRange(1, 247)
        self.slave_id_input.setValue(1)
        connection_layout.addRow("Slave ID:", self.slave_id_input)
        
        self.poll_interval_input = QSpinBox()
        self.poll_interval_input.setRange(100, 10000)
        self.poll_interval_input.setValue(1000)
        self.poll_interval_input.setSuffix(" мс")
        connection_layout.addRow("Poll Interval:", self.poll_interval_input)
        
        connection_group.setLayout(connection_layout)
        main_layout.addWidget(connection_group)
        
        # Кнопки управления
        button_layout = QHBoxLayout()
        
        self.connect_btn = QPushButton("Подключиться")
        self.connect_btn.clicked.connect(self.toggle_connection)
        button_layout.addWidget(self.connect_btn)
        
        self.read_coils_btn = QPushButton("Read Coils (01)")
        self.read_coils_btn.clicked.connect(lambda: self.read_data(1))
        button_layout.addWidget(self.read_coils_btn)
        
        self.read_discrete_btn = QPushButton("Read Discrete Inputs (02)")
        self.read_discrete_btn.clicked.connect(lambda: self.read_data(2))
        button_layout.addWidget(self.read_discrete_btn)
        
        self.read_holding_btn = QPushButton("Read Holding Registers (03)")
        self.read_holding_btn.clicked.connect(lambda: self.read_data(3))
        button_layout.addWidget(self.read_holding_btn)
        
        self.read_input_btn = QPushButton("Read Input Registers (04)")
        self.read_input_btn.clicked.connect(lambda: self.read_data(4))
        button_layout.addWidget(self.read_input_btn)
        
        main_layout.addLayout(button_layout)
        
        # Параметры запроса
        request_group = QGroupBox("Параметры запроса")
        request_layout = QFormLayout()
        
        self.start_address_input = QSpinBox()
        self.start_address_input.setRange(0, 65535)
        self.start_address_input.setValue(0)
        request_layout.addRow("Start Address:", self.start_address_input)
        
        self.quantity_input = QSpinBox()
        self.quantity_input.setRange(1, 125)
        self.quantity_input.setValue(10)
        request_layout.addRow("Quantity:", self.quantity_input)
        
        request_group.setLayout(request_layout)
        main_layout.addWidget(request_group)
        
        # Таблица результатов
        self.result_table = QTableWidget()
        self.result_table.setColumnCount(4)
        self.result_table.setHorizontalHeaderLabels([
            "Address", "Value", "Binary", "Hex"
        ])
        self.result_table.horizontalHeader().setStretchLastSection(True)
        main_layout.addWidget(self.result_table)
        
        # Статус бар
        self.status_label = QLabel("Статус: Отключено")
        self.status_label.setStyleSheet("color: gray;")
        main_layout.addWidget(self.status_label)
        
    def toggle_connection(self):
        if self.is_polling:
            self.disconnect()
        else:
            self.connect()
    
    def connect(self):
        try:
            if self.tcp_radio.isChecked():
                host = self.host_input.text()
                port = self.port_input.value()
                self.client = ModbusTcpClient(host=host, port=port)
            else:
                port = self.serial_port_input.currentText()
                baudrate = self.baud_rate_input.value()
                self.client = ModbusSerialClient(
                    port=port,
                    baudrate=baudrate,
                    parity='N',
                    stopbits=1,
                    bytesize=8
                )
            
            if not self.client.connect():
                raise Exception("Не удалось подключиться")
            
            self.is_polling = True
            self.connect_btn.setText("Отключиться")
            self.connect_btn.setStyleSheet("background-color: #ff6b6b; color: white;")
            self.status_label.setText("Статус: Подключено")
            self.status_label.setStyleSheet("color: green;")
            
            # Запуск автоматического опроса
            self.timer.start(self.poll_interval_input.value())
            
        except Exception as e:
            QMessageBox.critical(self, "Ошибка подключения", str(e))
            self.is_polling = False
    
    def disconnect(self):
        try:
            self.timer.stop()
            if self.client:
                self.client.close()
            self.is_polling = False
            self.connect_btn.setText("Подключиться")
            self.connect_btn.setStyleSheet("")
            self.status_label.setText("Статус: Отключено")
            self.status_label.setStyleSheet("color: gray;")
        except Exception as e:
            QMessageBox.warning(self, "Ошибка отключения", str(e))
    
    def read_data(self, function_code):
        if not self.client or not self.client.connected:
            QMessageBox.warning(self, "Ошибка", "Сначала подключитесь к устройству")
            return
        
        try:
            start_addr = self.start_address_input.value()
            quantity = self.quantity_input.value()
            slave_id = self.slave_id_input.value()
            
            result = None
            
            if function_code == 1:  # Read Coils
                result = self.client.read_coils(start_addr, quantity, slave=slave_id)
            elif function_code == 2:  # Read Discrete Inputs
                result = self.client.read_discrete_inputs(start_addr, quantity, slave=slave_id)
            elif function_code == 3:  # Read Holding Registers
                result = self.client.read_holding_registers(start_addr, quantity, slave=slave_id)
            elif function_code == 4:  # Read Input Registers
                result = self.client.read_input_registers(start_addr, quantity, slave=slave_id)
            
            if result and not result.isError():
                self.display_results(result, function_code, start_addr)
                self.status_label.setText(f"Статус: Успешно (FC{function_code})")
                self.status_label.setStyleSheet("color: green;")
            else:
                self.status_label.setText(f"Статус: Ошибка (FC{function_code})")
                self.status_label.setStyleSheet("color: red;")
                
        except Exception as e:
            QMessageBox.critical(self, "Ошибка чтения", str(e))
            self.status_label.setText(f"Статус: Ошибка - {str(e)}")
            self.status_label.setStyleSheet("color: red;")
    
    def poll_data(self):
        """Автоматический опрос данных"""
        if self.is_polling and self.client and self.client.connected:
            # По умолчанию опрашиваем Holding Registers
            self.read_data(3)
    
    def display_results(self, result, function_code, start_addr):
        """Отображение результатов в таблице"""
        self.result_table.setRowCount(0)
        
        if function_code in [1, 2]:  # Coils или Discrete Inputs
            for i, value in enumerate(result.bits):
                row = self.result_table.rowCount()
                self.result_table.insertRow(row)
                
                addr_item = QTableWidgetItem(str(start_addr + i))
                value_item = QTableWidgetItem(str(int(value)))
                binary_item = QTableWidgetItem(format(int(value), '08b'))
                hex_item = QTableWidgetItem(format(int(value), '02X'))
                
                self.result_table.setItem(row, 0, addr_item)
                self.result_table.setItem(row, 1, value_item)
                self.result_table.setItem(row, 2, binary_item)
                self.result_table.setItem(row, 3, hex_item)
                
        elif function_code in [3, 4]:  # Registers
            for i, value in enumerate(result.registers):
                row = self.result_table.rowCount()
                self.result_table.insertRow(row)
                
                addr_item = QTableWidgetItem(str(start_addr + i))
                value_item = QTableWidgetItem(str(value))
                binary_item = QTableWidgetItem(format(value & 0xFFFF, '016b'))
                hex_item = QTableWidgetItem(format(value & 0xFFFF, '04X'))
                
                self.result_table.setItem(row, 0, addr_item)
                self.result_table.setItem(row, 1, value_item)
                self.result_table.setItem(row, 2, binary_item)
                self.result_table.setItem(row, 3, hex_item)
        
        self.result_table.resizeColumnsToContents()
    
    def closeEvent(self, event):
        """Обработка закрытия окна"""
        if self.is_polling:
            self.disconnect()
        event.accept()


def main():
    app = QApplication(sys.argv)
    window = ModbusClientApp()
    window.show()
    sys.exit(app.exec())


if __name__ == "__main__":
    main()
