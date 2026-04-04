#!/usr/bin/env python3
"""
Modbus Client GUI - Аналог Modbus Poll
Поддерживает Modbus TCP и Modbus RTU (через последовательный порт)

Архитектура:
- ModbusHandler: Бизнес-логика работы с Modbus
- ModbusClientApp: GUI приложение
"""

import sys
import threading
from typing import Optional, List, Tuple, Any
from dataclasses import dataclass
from enum import IntEnum

from PyQt6.QtWidgets import (
    QApplication, QMainWindow, QWidget, QVBoxLayout, QHBoxLayout,
    QLabel, QLineEdit, QPushButton, QComboBox, QSpinBox, QTableWidget,
    QTableWidgetItem, QGroupBox, QFormLayout, QMessageBox, QTabWidget,
    QRadioButton, QButtonGroup, QStatusBar
)
from PyQt6.QtCore import QTimer, Qt, pyqtSignal, QObject
from pymodbus.client import ModbusTcpClient, ModbusSerialClient
from pymodbus.constants import Endian
from pymodbus.payload import BinaryPayloadDecoder
from pymodbus.exceptions import ModbusException, ConnectionException


class FunctionCode(IntEnum):
    """Коды функций Modbus"""
    READ_COILS = 1
    READ_DISCRETE_INPUTS = 2
    READ_HOLDING_REGISTERS = 3
    READ_INPUT_REGISTERS = 4


@dataclass
class ModbusConfig:
    """Конфигурация подключения Modbus"""
    # TCP параметры
    host: str = "127.0.0.1"
    port: int = 502
    
    # RTU параметры
    serial_port: str = "/dev/ttyUSB0"
    baudrate: int = 9600
    parity: str = 'N'
    stopbits: int = 1
    bytesize: int = 8
    
    # Общие параметры
    slave_id: int = 1
    poll_interval: int = 1000  # мс
    is_tcp: bool = True


@dataclass
class ReadResult:
    """Результат чтения данных"""
    address: int
    value: Any
    binary: str
    hex: str
    function_code: int


class ModbusHandler(QObject):
    """Обработчик Modbus соединений и операций"""
    
    connected = pyqtSignal(bool)
    data_received = pyqtSignal(list)
    error_occurred = pyqtSignal(str)
    
    def __init__(self):
        super().__init__()
        self.client: Optional[Any] = None
        self.is_connected: bool = False
        self._lock = threading.Lock()
    
    def connect(self, config: ModbusConfig) -> bool:
        """Установить соединение с устройством"""
        with self._lock:
            try:
                if config.is_tcp:
                    self.client = ModbusTcpClient(
                        host=config.host,
                        port=config.port
                    )
                else:
                    self.client = ModbusSerialClient(
                        port=config.serial_port,
                        baudrate=config.baudrate,
                        parity=config.parity,
                        stopbits=config.stopbits,
                        bytesize=config.bytesize
                    )
                
                if not self.client.connect():
                    raise ConnectionException("Не удалось подключиться")
                
                self.is_connected = True
                self.connected.emit(True)
                return True
                
            except Exception as e:
                self.error_occurred.emit(f"Ошибка подключения: {str(e)}")
                self.is_connected = False
                return False
    
    def disconnect(self) -> None:
        """Разорвать соединение"""
        with self._lock:
            try:
                if self.client:
                    self.client.close()
                self.is_connected = False
                self.connected.emit(False)
            except Exception as e:
                self.error_occurred.emit(f"Ошибка отключения: {str(e)}")
    
    def read_data(
        self,
        function_code: FunctionCode,
        start_address: int,
        quantity: int,
        slave_id: int
    ) -> Optional[List[ReadResult]]:
        """Прочитать данные с устройства"""
        with self._lock:
            if not self.client or not self.is_connected:
                self.error_occurred.emit("Нет соединения")
                return None
            
            try:
                result = None
                
                if function_code == FunctionCode.READ_COILS:
                    result = self.client.read_coils(
                        start_address, quantity, slave=slave_id
                    )
                elif function_code == FunctionCode.READ_DISCRETE_INPUTS:
                    result = self.client.read_discrete_inputs(
                        start_address, quantity, slave=slave_id
                    )
                elif function_code == FunctionCode.READ_HOLDING_REGISTERS:
                    result = self.client.read_holding_registers(
                        start_address, quantity, slave=slave_id
                    )
                elif function_code == FunctionCode.READ_INPUT_REGISTERS:
                    result = self.client.read_input_registers(
                        start_address, quantity, slave=slave_id
                    )
                
                if result and not result.isError():
                    return self._parse_result(
                        result, function_code, start_address
                    )
                else:
                    self.error_occurred.emit(
                        f"Ошибка Modbus (FC{function_code.value})"
                    )
                    return None
                    
            except ModbusException as e:
                self.error_occurred.emit(f"Modbus ошибка: {str(e)}")
                return None
            except Exception as e:
                self.error_occurred.emit(f"Ошибка чтения: {str(e)}")
                return None
    
    def _parse_result(
        self,
        result: Any,
        function_code: FunctionCode,
        start_address: int
    ) -> List[ReadResult]:
        """Преобразовать результат в список ReadResult"""
        results = []
        
        if function_code in [FunctionCode.READ_COILS, 
                            FunctionCode.READ_DISCRETE_INPUTS]:
            for i, value in enumerate(result.bits):
                int_value = int(value)
                results.append(ReadResult(
                    address=start_address + i,
                    value=int_value,
                    binary=format(int_value, '08b'),
                    hex=format(int_value, '02X'),
                    function_code=function_code.value
                ))
        
        elif function_code in [FunctionCode.READ_HOLDING_REGISTERS,
                              FunctionCode.READ_INPUT_REGISTERS]:
            for i, value in enumerate(result.registers):
                masked_value = value & 0xFFFF
                results.append(ReadResult(
                    address=start_address + i,
                    value=value,
                    binary=format(masked_value, '016b'),
                    hex=format(masked_value, '04X'),
                    function_code=function_code.value
                ))
        
        return results


class ModbusClientApp(QMainWindow):
    """Основное окно приложения Modbus Client"""
    
    def __init__(self):
        super().__init__()
        self.setWindowTitle("Modbus Client - Аналог Modbus Poll")
        self.setGeometry(100, 100, 1200, 800)
        
        self.modbus_handler = ModbusHandler()
        self.config = ModbusConfig()
        self.timer = QTimer()
        self.timer.timeout.connect(self.poll_data)
        
        self._setup_ui()
        self._connect_signals()
    
    def _setup_ui(self) -> None:
        """Инициализация пользовательского интерфейса"""
        central_widget = QWidget()
        self.setCentralWidget(central_widget)
        main_layout = QVBoxLayout(central_widget)
        
        # Настройки подключения
        connection_group = self._create_connection_group()
        main_layout.addWidget(connection_group)
        
        # Кнопки управления
        button_layout = self._create_button_layout()
        main_layout.addLayout(button_layout)
        
        # Параметры запроса
        request_group = self._create_request_group()
        main_layout.addWidget(request_group)
        
        # Таблица результатов
        self.result_table = self._create_result_table()
        main_layout.addWidget(self.result_table)
        
        # Статус бар
        self.statusbar = QStatusBar()
        self.setStatusBar(self.statusbar)
        self.statusbar.showMessage("Статус: Отключено")
    
    def _create_connection_group(self) -> QGroupBox:
        """Создать группу настроек подключения"""
        group = QGroupBox("Настройки подключения")
        layout = QFormLayout()
        
        # Тип подключения
        self.tcp_radio = QRadioButton("Modbus TCP")
        self.tcp_radio.setChecked(True)
        self.rtu_radio = QRadioButton("Modbus RTU (Serial)")
        
        type_layout = QHBoxLayout()
        type_layout.addWidget(self.tcp_radio)
        type_layout.addWidget(self.rtu_radio)
        self.type_group = QButtonGroup()
        self.type_group.addButton(self.tcp_radio)
        self.type_group.addButton(self.rtu_radio)
        
        layout.addRow(type_layout)
        
        # Параметры TCP
        self.host_input = QLineEdit("127.0.0.1")
        self.host_input.setPlaceholderText("IP адрес")
        layout.addRow("Host:", self.host_input)
        
        self.port_input = QSpinBox()
        self.port_input.setRange(1, 65535)
        self.port_input.setValue(502)
        layout.addRow("Port:", self.port_input)
        
        # Параметры RTU
        self.serial_port_input = QComboBox()
        self.serial_port_input.addItems([
            "/dev/ttyUSB0", "/dev/ttyS0", "COM1", "COM2"
        ])
        self.serial_port_input.setEditable(True)
        layout.addRow("Serial Port:", self.serial_port_input)
        
        self.baud_rate_input = QSpinBox()
        self.baud_rate_input.setRange(1200, 115200)
        self.baud_rate_input.setValue(9600)
        layout.addRow("Baud Rate:", self.baud_rate_input)
        
        # Общие параметры
        self.slave_id_input = QSpinBox()
        self.slave_id_input.setRange(1, 247)
        self.slave_id_input.setValue(1)
        layout.addRow("Slave ID:", self.slave_id_input)
        
        self.poll_interval_input = QSpinBox()
        self.poll_interval_input.setRange(100, 10000)
        self.poll_interval_input.setValue(1000)
        self.poll_interval_input.setSuffix(" мс")
        layout.addRow("Poll Interval:", self.poll_interval_input)
        
        group.setLayout(layout)
        return group
    
    def _create_button_layout(self) -> QHBoxLayout:
        """Создать панель кнопок управления"""
        layout = QHBoxLayout()
        
        self.connect_btn = QPushButton("Подключиться")
        self.connect_btn.clicked.connect(self.toggle_connection)
        layout.addWidget(self.connect_btn)
        
        self.read_coils_btn = QPushButton("Read Coils (01)")
        self.read_coils_btn.clicked.connect(
            lambda: self.read_data(FunctionCode.READ_COILS)
        )
        layout.addWidget(self.read_coils_btn)
        
        self.read_discrete_btn = QPushButton("Read Discrete Inputs (02)")
        self.read_discrete_btn.clicked.connect(
            lambda: self.read_data(FunctionCode.READ_DISCRETE_INPUTS)
        )
        layout.addWidget(self.read_discrete_btn)
        
        self.read_holding_btn = QPushButton("Read Holding Registers (03)")
        self.read_holding_btn.clicked.connect(
            lambda: self.read_data(FunctionCode.READ_HOLDING_REGISTERS)
        )
        layout.addWidget(self.read_holding_btn)
        
        self.read_input_btn = QPushButton("Read Input Registers (04)")
        self.read_input_btn.clicked.connect(
            lambda: self.read_data(FunctionCode.READ_INPUT_REGISTERS)
        )
        layout.addWidget(self.read_input_btn)
        
        return layout
    
    def _create_request_group(self) -> QGroupBox:
        """Создать группу параметров запроса"""
        group = QGroupBox("Параметры запроса")
        layout = QFormLayout()
        
        self.start_address_input = QSpinBox()
        self.start_address_input.setRange(0, 65535)
        self.start_address_input.setValue(0)
        layout.addRow("Start Address:", self.start_address_input)
        
        self.quantity_input = QSpinBox()
        self.quantity_input.setRange(1, 125)
        self.quantity_input.setValue(10)
        layout.addRow("Quantity:", self.quantity_input)
        
        group.setLayout(layout)
        return group
    
    def _create_result_table(self) -> QTableWidget:
        """Создать таблицу результатов"""
        table = QTableWidget()
        table.setColumnCount(4)
        table.setHorizontalHeaderLabels([
            "Address", "Value", "Binary", "Hex"
        ])
        table.horizontalHeader().setStretchLastSection(True)
        return table
    
    def _connect_signals(self) -> None:
        """Подключить сигналы обработчика"""
        self.modbus_handler.connected.connect(self.on_connection_changed)
        self.modbus_handler.data_received.connect(self.display_results)
        self.modbus_handler.error_occurred.connect(self.show_error)
    
    def toggle_connection(self) -> None:
        """Переключить состояние подключения"""
        if self.modbus_handler.is_connected:
            self.disconnect()
        else:
            self.connect()
    
    def connect(self) -> None:
        """Подключиться к устройству"""
        self.config = self._get_config_from_ui()
        success = self.modbus_handler.connect(self.config)
        if success:
            self.timer.start(self.config.poll_interval)
    
    def disconnect(self) -> None:
        """Отключиться от устройства"""
        self.timer.stop()
        self.modbus_handler.disconnect()
    
    def on_connection_changed(self, connected: bool) -> None:
        """Обработка изменения состояния подключения"""
        if connected:
            self.connect_btn.setText("Отключиться")
            self.connect_btn.setStyleSheet(
                "background-color: #ff6b6b; color: white;"
            )
            self.statusbar.showMessage("Статус: Подключено")
            self.statusbar.setStyleSheet("color: green;")
        else:
            self.connect_btn.setText("Подключиться")
            self.connect_btn.setStyleSheet("")
            self.statusbar.showMessage("Статус: Отключено")
            self.statusbar.setStyleSheet("color: gray;")
    
    def read_data(self, function_code: FunctionCode) -> None:
        """Выполнить чтение данных"""
        if not self.modbus_handler.is_connected:
            QMessageBox.warning(
                self, "Ошибка", "Сначала подключитесь к устройству"
            )
            return
        
        results = self.modbus_handler.read_data(
            function_code=function_code,
            start_address=self.start_address_input.value(),
            quantity=self.quantity_input.value(),
            slave_id=self.slave_id_input.value()
        )
        
        if results:
            self.statusbar.showMessage(
                f"Статус: Успешно (FC{function_code.value})"
            )
            self.statusbar.setStyleSheet("color: green;")
    
    def poll_data(self) -> None:
        """Автоматический опрос данных (Holding Registers)"""
        if self.modbus_handler.is_connected:
            self.read_data(FunctionCode.READ_HOLDING_REGISTERS)
    
    def display_results(self, results: List[ReadResult]) -> None:
        """Отобразить результаты в таблице"""
        self.result_table.setRowCount(0)
        
        for result in results:
            row = self.result_table.rowCount()
            self.result_table.insertRow(row)
            
            self.result_table.setItem(
                row, 0, QTableWidgetItem(str(result.address))
            )
            self.result_table.setItem(
                row, 1, QTableWidgetItem(str(result.value))
            )
            self.result_table.setItem(
                row, 2, QTableWidgetItem(result.binary)
            )
            self.result_table.setItem(
                row, 3, QTableWidgetItem(result.hex)
            )
        
        self.result_table.resizeColumnsToContents()
    
    def show_error(self, message: str) -> None:
        """Показать сообщение об ошибке"""
        self.statusbar.showMessage(f"Статус: Ошибка - {message}")
        self.statusbar.setStyleSheet("color: red;")
    
    def _get_config_from_ui(self) -> ModbusConfig:
        """Получить конфигурацию из элементов UI"""
        return ModbusConfig(
            host=self.host_input.text(),
            port=self.port_input.value(),
            serial_port=self.serial_port_input.currentText(),
            baudrate=self.baud_rate_input.value(),
            slave_id=self.slave_id_input.value(),
            poll_interval=self.poll_interval_input.value(),
            is_tcp=self.tcp_radio.isChecked()
        )
    
    def closeEvent(self, event) -> None:
        """Обработка закрытия окна"""
        if self.modbus_handler.is_connected:
            self.disconnect()
        event.accept()


def main():
    app = QApplication(sys.argv)
    window = ModbusClientApp()
    window.show()
    sys.exit(app.exec())


if __name__ == "__main__":
    main()
