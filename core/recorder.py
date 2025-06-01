import json
import time
from typing import List, Dict, Any, Optional, Tuple
from pynput import mouse, keyboard
import logging
import os
from datetime import datetime
import configparser
import math
# numpy e deque não são usados atualmente, podem ser removidos se não planejados para uso futuro
# import numpy as np 
# from collections import deque
import threading # Adicionado para a thread de verificação de ação

# Configurar logging
logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(name)s - %(levelname)s - %(message)s')
logger = logging.getLogger(__name__)

class EventRecorder:
    def __init__(self):
        self.script_dir = os.path.dirname(os.path.abspath(__file__))
        self.project_root = os.path.dirname(self.script_dir)

        self.events: List[Dict[str, Any]] = []
        self.start_time: Optional[float] = None 
        self.is_recording: bool = False
        
        self.mouse_listener: Optional[mouse.Listener] = None
        self.keyboard_listener: Optional[keyboard.Listener] = None # Para eventos de dados
        
        self.config = self._load_config()
        
        self.last_mouse_position: Optional[Tuple[int, int]] = None
        self.last_mouse_time: Optional[float] = None
        
        self.last_event_time: Optional[float] = None
        self.pause_threshold = self.config.getfloat('Recording', 'pause_threshold', fallback=0.05)
        
        self.button_press_times: Dict[str, float] = {}
        
        self.screen_width = 1920 
        self.screen_height = 1080 
        self._initialize_screen_info()
        
        self.current_action: Optional[str] = None
        self.action_start_time: Optional[float] = None
        self.action_events: List[Dict[str, Any]] = []
        
        _suggested_actions_path_config = self.config.get('Paths', 'suggested_actions', fallback='suggested_actions.txt')
        if not os.path.isabs(_suggested_actions_path_config):
            self.suggested_actions_file = os.path.join(self.project_root, _suggested_actions_path_config)
        else:
            self.suggested_actions_file = _suggested_actions_path_config
        logger.info(f"Caminho do arquivo de ações sugeridas resolvido para: {self.suggested_actions_file}")

        self.last_action_check_time = 0.0
        self.action_check_interval = self.config.getfloat('Recording', 'action_check_interval', fallback=0.5)

    def _initialize_screen_info(self) -> None:
        try:
            import pyautogui
            self.screen_width, self.screen_height = pyautogui.size()
            logger.info(f"Tamanho da tela detectado: {self.screen_width}x{self.screen_height}")
        except ImportError: 
            logger.warning("pyautogui não encontrado. Usando tamanho de tela padrão 1920x1080.")
        except Exception as e: 
            logger.error(f"Falha ao obter o tamanho da tela usando pyautogui: {str(e)}. Usando padrão.")

    def _load_config(self) -> configparser.ConfigParser:
        config = configparser.ConfigParser()
        config_path = os.path.join(self.project_root, 'config.ini') 
        if not os.path.exists(config_path):
            logger.warning(f"Arquivo de configuração não encontrado em {config_path}. Usando valores padrão.")
            config['Paths'] = {'patterns_directory': 'patterns', 'suggested_actions': 'suggested_actions.txt'}
            config['Recording'] = {'pause_threshold': '0.05', 'action_check_interval': '0.5'}
            # Removido Analysis -> movement_history_size pois não é usado
            config['Hotkeys'] = {'start_recording': 'Key.f2', 'stop_recording': 'Key.f3'}
            return config
        config.read(config_path)
        logger.info(f"Configuração carregada de {config_path}")
        return config

    def _get_time_offset(self) -> int:
        if self.start_time is None: return 0
        return int((time.time() - self.start_time) * 1000)

    def _parse_action_line(self, action_line: str) -> Tuple[Optional[str], Optional[int]]:
        if not action_line: return None, None
        try:
            # Remove timestamp potencial como "YYYY-MM-DD HH:MM:SS - "
            if " - " in action_line and action_line.count(':') >= 2: 
                action_line = action_line.split(" - ", 1)[1]
            
            box_id: Optional[int] = None
            action_type_str: str = action_line.strip()

            if '[' in action_type_str and action_type_str.endswith(']'):
                try:
                    action_name_part = action_type_str[:action_type_str.rfind('[')].strip()
                    box_id_str = action_type_str[action_type_str.rfind('[')+1:-1]
                    box_id = int(box_id_str)
                    action_type_str = action_name_part
                except ValueError:
                    logger.warning(f"Não foi possível analisar box_id de '{action_line}'. Tratando como nome de ação.")
                    action_type_str = action_line.strip() 
                    box_id = None
            return action_type_str, box_id
        except Exception as e:
            logger.error(f"Erro ao analisar linha de ação '{action_line}': {str(e)}")
            return action_line.strip(), None

    def _check_for_new_action_from_file(self) -> None:
        current_time = time.time()
        if current_time - self.last_action_check_time < self.action_check_interval:
            return 
        self.last_action_check_time = current_time
        
        try:
            if os.path.exists(self.suggested_actions_file):
                with open(self.suggested_actions_file, 'r', encoding='utf-8') as f:
                    lines = f.readlines()
                    if lines:
                        new_action_line = lines[0].strip()
                        if not new_action_line: return

                        if new_action_line != self.current_action:
                            logger.info(f"Nova linha de ação detectada: '{new_action_line}'")
                            # Salva a ação anterior somente se a gravação tiver sido iniciada
                            if self.current_action and self.action_events and self.start_time is not None:
                                logger.info(f"Salvando ação anterior: {self.current_action}")
                                self.save_recording_for_action(self.current_action, self.action_events)
                            
                            self.current_action = new_action_line
                            self.action_start_time = current_time 
                            self.action_events = [] 
                            logger.info(f"Mundando para nova ação: {self.current_action}")
        except Exception as e:
            logger.error(f"Erro ao verificar novas ações do arquivo: {str(e)}")

    def _check_for_pause(self, current_event_time: float) -> None:
        if not self.start_time: # Gravação não iniciada
            return
        
        if self.last_event_time is None: # Primeiro evento da gravação
            self.last_event_time = current_event_time
            return

        time_since_last_event = current_event_time - self.last_event_time
        
        if time_since_last_event >= self.pause_threshold:
            pause_start_time = self.last_event_time 
            pause_duration = time_since_last_event
            
            pause_event_x = self.last_mouse_position[0] if self.last_mouse_position else 0
            pause_event_y = self.last_mouse_position[1] if self.last_mouse_position else 0

            event_data = {
                'type': 'pause',
                'time_offset_ms': int((pause_start_time - self.start_time) * 1000),
                'duration_ms': int(pause_duration * 1000),
                'x': pause_event_x, 
                'y': pause_event_y,
                'timestamp': pause_start_time 
            }
            self.events.append(event_data)
            if self.current_action:
                self.action_events.append(event_data)
            logger.debug(f"Pausa registrada: duração {pause_duration:.3f}s, começando no offset {event_data['time_offset_ms']}")
        
        # Atualiza o tempo do último evento para o timestamp do evento atual sendo processado
        self.last_event_time = current_event_time

    def _on_mouse_move(self, x: int, y: int) -> None:
        if not self.is_recording or self.start_time is None: return
        current_time = time.time()
        self._check_for_pause(current_time)
        
        dt = (current_time - self.last_mouse_time) if self.last_mouse_time is not None else 0.0
        
        dx, dy, distance, speed, angle = 0, 0, 0.0, 0.0, 0.0
        if self.last_mouse_position is not None:
            dx = x - self.last_mouse_position[0]
            dy = y - self.last_mouse_position[1]
            distance = math.sqrt(dx*dx + dy*dy)
            if dt > 1e-6: # Evita divisão por zero ou dt muito pequeno
                speed = distance / dt
            angle = math.atan2(dy, dx) * 180 / math.pi
        
        movement_metrics = {
            'dt': dt, 'distance': distance, 'speed': speed, 
            'angle': angle, 'dx': dx, 'dy': dy
        }
        
        event = {
            'type': 'mouse_move', 'time_offset_ms': self._get_time_offset(), 
            'x': x, 'y': y, 'timestamp': current_time, 
            'movement_metrics': movement_metrics 
        }
        self.events.append(event)
        if self.current_action: self.action_events.append(event)
        
        self.last_mouse_position = (x, y)
        self.last_mouse_time = current_time
        # self.last_event_time é atualizado por _check_for_pause

    def _on_mouse_click(self, x: int, y: int, button: mouse.Button, pressed: bool) -> None:
        if not self.is_recording or self.start_time is None: return
        current_time = time.time()
        self._check_for_pause(current_time)

        button_str = str(button)
        event_type = 'mouse_click_press' if pressed else 'mouse_click_release'
        
        event_data: Dict[str, Any] = {
            'type': event_type, 'time_offset_ms': self._get_time_offset(), 
            'x': x, 'y': y, 'button': button_str, 'timestamp': current_time
        }

        if pressed:
            self.button_press_times[button_str] = current_time
        else:
            press_time = self.button_press_times.pop(button_str, current_time) # Default to current_time if not found to avoid error
            hold_duration_ms = int((current_time - press_time) * 1000)
            event_data['hold_duration_ms'] = hold_duration_ms
        
        self.events.append(event_data)
        if self.current_action: self.action_events.append(event_data)
        
        self.last_mouse_position = (x,y) 
        # self.last_event_time é atualizado por _check_for_pause

    def _on_key_event(self, key_obj: Any, event_type: str) -> None:
        if not self.is_recording or self.start_time is None: return
        current_time = time.time()
        self._check_for_pause(current_time)

        key_str = ""
        try: # Tenta obter char para teclas normais
            key_str = key_obj.char
            if key_str is None: # Para algumas teclas especiais que podem ter char=None
                 key_str = str(key_obj)
        except AttributeError: # Para teclas especiais (ex: Key.space, Key.f1)
            key_str = str(key_obj)
        
        event_data: Dict[str, Any] = {
            'type': event_type, 'time_offset_ms': self._get_time_offset(), 
            'key': key_str, 'timestamp': current_time
        }

        if event_type == 'key_press':
            self.button_press_times[key_str] = current_time
        elif event_type == 'key_release':
            press_time = self.button_press_times.pop(key_str, current_time)
            hold_duration_ms = int((current_time - press_time) * 1000)
            event_data['hold_duration_ms'] = hold_duration_ms
            
        self.events.append(event_data)
        if self.current_action: self.action_events.append(event_data)
        # self.last_event_time é atualizado por _check_for_pause

    def _on_key_press(self, key: keyboard.Key) -> None: self._on_key_event(key, 'key_press')
    def _on_key_release(self, key: keyboard.Key) -> None: self._on_key_event(key, 'key_release')

    def start_recording(self) -> None:
        if self.is_recording:
            logger.warning("A gravação já está em progresso")
            return

        self.events = []
        self.action_events = [] 
        self.start_time = time.time() # Marca o início da sessão de gravação
        self.is_recording = True
        
        self.last_mouse_position = None
        # Inicializa last_mouse_time para o tempo de início para o primeiro cálculo de dt
        self.last_mouse_time = self.start_time 
        self.last_event_time = self.start_time # Inicializa para detecção de pausa
        self.button_press_times = {}
        
        self.current_action = None 
        self.action_start_time = self.start_time 
        self.last_action_check_time = self.start_time # Reseta timer de verificação de ação
        self._check_for_new_action_from_file() # Tenta carregar ação inicial
        if not self.current_action:
            logger.info("Nenhuma ação inicial especificada em suggested_actions.txt. Gravação será geral.")

        self.mouse_listener = mouse.Listener(on_move=self._on_mouse_move, on_click=self._on_mouse_click)
        self.mouse_listener.start()
        self.keyboard_listener = keyboard.Listener(on_press=self._on_key_press, on_release=self._on_key_release)
        self.keyboard_listener.start()
        logger.info("Gravação de eventos iniciada.")

    def _trigger_stop_sequence(self) -> None:
        """Inicia a sequência para parar a gravação, parando a captura de dados."""
        if not self.is_recording and self.start_time is None:
            logger.debug("Sequência de parada acionada, mas gravação não estava ativa ou não foi iniciada.")
            return

        logger.info("Sinal de parada recebido. Parando captura de dados...")
        self.is_recording = False # Impede que novos eventos sejam processados pelos callbacks

        # Para listeners de dados
        if self.mouse_listener:
            logger.debug("Parando listener de mouse...")
            self.mouse_listener.stop()
        
        if self.keyboard_listener: # Listener de dados do teclado
            logger.debug("Parando listener de teclado (dados)...")
            self.keyboard_listener.stop()
        # Joins para esses listeners ocorrerão no bloco finally de run_hotkey_listener

    def _handle_hotkey_press(self, key: Any) -> Optional[bool]:
        """Lida com pressionamentos de hotkey (executa na thread do listener de hotkeys)."""
        start_hotkey_str = self.config.get('Hotkeys', 'start_recording', fallback='Key.f2')
        stop_hotkey_str = self.config.get('Hotkeys', 'stop_recording', fallback='Key.f3')

        key_pressed_str = ""
        if isinstance(key, keyboard.Key): # Teclas especiais
            key_pressed_str = str(key) 
        elif isinstance(key, keyboard.KeyCode): # Teclas alfanuméricas
            if key.char: key_pressed_str = key.char

        # Normaliza a string da tecla pressionada (ex: remove aspas de caracteres)
        if len(key_pressed_str) == 3 and key_pressed_str.startswith("'") and key_pressed_str.endswith("'"):
            key_pressed_str = key_pressed_str[1]

        if key_pressed_str == start_hotkey_str:
            if not self.is_recording:
                logger.info(f"Hotkey '{start_hotkey_str}' pressionada - Iniciando gravação")
                self.start_recording()
            else:
                logger.info(f"Hotkey '{start_hotkey_str}' pressionada, mas já gravando.")
        elif key_pressed_str == stop_hotkey_str:
            # Verifica se a gravação está ativa ou foi iniciada
            if self.is_recording or self.start_time is not None:
                logger.info(f"Hotkey '{stop_hotkey_str}' pressionada - Sinalizando parada da gravação.")
                self._trigger_stop_sequence() # Para a captura de dados
                return False # IMPORTANTE: Para este listener de hotkeys
            else:
                logger.info(f"Hotkey '{stop_hotkey_str}' pressionada, mas não gravando ou não iniciada.")
        return None # Continua escutando por padrão

    def run_hotkey_listener(self) -> None:
        """Executa o listener de hotkeys na thread atual. Bloqueante até ser parado."""
        start_hk = self.config.get('Hotkeys', 'start_recording', fallback='Key.f2')
        stop_hk = self.config.get('Hotkeys', 'stop_recording', fallback='Key.f3')
        logger.info(f"Listener de hotkeys iniciado. Pressione '{start_hk}' para iniciar, '{stop_hk}' para parar.")
        
        action_check_active = True
        action_check_thread = None

        def _periodic_action_check():
            while action_check_active:
                if self.is_recording: # Somente verifica se estiver gravando ativamente
                    self._check_for_new_action_from_file()
                time.sleep(self.action_check_interval)
            logger.debug("Thread de verificação de ação periódica terminando.")

        action_check_thread = threading.Thread(target=_periodic_action_check, daemon=True)
        action_check_thread.start()

        try:
            # O listener de hotkeys principal
            with keyboard.Listener(on_press=self._handle_hotkey_press) as k_listener:
                k_listener.join() # Bloqueia aqui até on_press retornar False ou erro
            logger.debug("Listener de hotkeys principal (keyboard.Listener) terminou normalmente.")

        except KeyboardInterrupt:
            logger.info("Interrupção de teclado (Ctrl+C) recebida. Acionando parada...")
            self._trigger_stop_sequence() 
            # A saída do bloco 'with' garantirá que k_listener seja parado.
        except Exception as e:
            logger.error(f"Erro inesperado no listener de hotkeys: {e}", exc_info=True)
            self._trigger_stop_sequence() # Tenta parar a captura de dados
        finally:
            logger.info("Bloco finally do run_hotkey_listener alcançado.")
            action_check_active = False # Sinaliza a thread de verificação para parar
            if action_check_thread and action_check_thread.is_alive():
                logger.debug("Aguardando a thread de verificação de ação periódica terminar...")
                action_check_thread.join(timeout=max(1.0, self.action_check_interval * 2 + 0.1))
                if action_check_thread.is_alive():
                    logger.warning("Thread de verificação de ação periódica não terminou a tempo.")
            
            # Garante que os listeners de dados sejam juntados
            if self.mouse_listener and self.mouse_listener.is_alive():
                logger.debug("Joining mouse_listener no finally...")
                self.mouse_listener.join(timeout=1.0) 
            self.mouse_listener = None 
            
            if self.keyboard_listener and self.keyboard_listener.is_alive():
                logger.debug("Joining keyboard_listener (data) no finally...")
                self.keyboard_listener.join(timeout=1.0)
            self.keyboard_listener = None

            logger.info("Realizando limpeza final e salvamento...")
            
            # Salva somente se a gravação foi de fato iniciada
            if self.start_time is not None: 
                final_event_time = time.time() # Tempo para a verificação da pausa final
                # Verifica se uma pausa ocorreu entre o último evento e a parada
                if self.last_event_time and (final_event_time > self.last_event_time + self.pause_threshold):
                    logger.debug(f"Verificando pausa final. current_time: {final_event_time}, last_event_time: {self.last_event_time}")
                    self._check_for_pause(final_event_time)

                # Lógica de salvamento
                if self.current_action and self.action_events:
                    self.save_recording_for_action(self.current_action, self.action_events)
                elif not self.current_action and self.events: # Se não houver ação específica, mas houver eventos gerais
                    logger.info(f"Nenhum nome de ação específico. Salvando todos os {len(self.events)} eventos gravados com nome genérico.")
                    generic_action_name = f"recording_{datetime.now().strftime('%Y%m%d_%H%M%S')}"
                    self.save_recording_for_action(generic_action_name, self.events)
                elif not self.events: # Se self.events estiver vazio
                     logger.info("Nenhum evento foi gravado nesta sessão.")
                else: # Outras condições (ex: current_action existe mas action_events está vazio)
                    logger.info("Condição para salvamento não atendida (ex: ação atual sem eventos de ação).")
            else:
                logger.info("Gravação não foi iniciada ou nenhum evento significativo para salvar.")
            
            self.is_recording = False # Garante que o estado seja falso
            self.start_time = None # Reseta para a próxima sessão de gravação
            logger.info("Listener de hotkeys e limpeza finalizados.")

    def save_recording_for_action(self, action_name_line: str, events_to_save: List[Dict[str, Any]]) -> Optional[str]:
        """Salva os eventos fornecidos em um arquivo JSON para a linha de nome de ação especificada."""
        if not events_to_save:
            logger.warning(f"Nenhum evento para salvar para a ação: {action_name_line}")
            return None
        try:
            patterns_dir_config = self.config.get('Paths', 'patterns_directory', fallback='patterns')
            # Garante que patterns_dir seja absoluto
            if not os.path.isabs(patterns_dir_config):
                 abs_patterns_dir = os.path.join(self.project_root, patterns_dir_config)
            else:
                 abs_patterns_dir = patterns_dir_config
            os.makedirs(abs_patterns_dir, exist_ok=True)

            action_type, box_id = self._parse_action_line(action_name_line)
            action_type = action_type or "unknown_action" # Fallback
            
            safe_action_filename_base = "".join(c if c.isalnum() or c in ('_','-') else '_' for c in action_type)
            if box_id is not None:
                safe_action_filename_base = f"{safe_action_filename_base}_box{box_id}"

            timestamp_str = datetime.now().strftime("%Y%m%d_%H%M%S_%f") # Adicionado microssegundos
            filename = f"{safe_action_filename_base}_{timestamp_str}.json"
            filepath = os.path.join(abs_patterns_dir, filename)
            
            recording_data = {
                'action_name_line': action_name_line,
                'parsed_action_type': action_type,
                'parsed_box_id': box_id,
                'save_timestamp': datetime.now().isoformat(),
                'total_events': len(events_to_save),
                'events': events_to_save
            }
            with open(filepath, 'w', encoding='utf-8') as f:
                json.dump(recording_data, f, indent=2, ensure_ascii=False)
            logger.info(f"Salvos {len(events_to_save)} eventos com sucesso em: {filepath}")
            return filepath
        except Exception as e:
            logger.error(f"Falha ao salvar gravação para ação '{action_name_line}': {str(e)}", exc_info=True)
            return None

    def get_events(self) -> List[Dict[str, Any]]:
        """Retorna uma cópia da lista de todos os eventos gravados (lista mestre)."""
        return self.events.copy()


if __name__ == "__main__":
    recorder = EventRecorder()
    logger.info("Iniciando EventRecorder com suporte a hotkey.")
    logger.info(f"Arquivo de configuração esperado em: {os.path.join(recorder.project_root, 'config.ini')}")
    logger.info(f"Arquivo de ações sugeridas: {recorder.suggested_actions_file}") 
    
    patterns_dir_config_val = recorder.config.get('Paths', 'patterns_directory', fallback='patterns')
    resolved_patterns_dir = patterns_dir_config_val
    if not os.path.isabs(patterns_dir_config_val):
        resolved_patterns_dir = os.path.join(recorder.project_root, patterns_dir_config_val)
    logger.info(f"Diretório de padrões: {resolved_patterns_dir}")

    recorder.run_hotkey_listener()
    logger.info("Programa EventRecorder encerrado.")