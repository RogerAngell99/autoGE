import json
import time
from typing import List, Dict, Any, Optional, Tuple
from pynput import mouse, keyboard
import logging
import os
from datetime import datetime
import configparser
import math
import numpy as np # numpy não é usado no código atual, pode ser removido se não for necessário para futuras análises
from collections import deque

# Configurar logging
logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(name)s - %(levelname)s - %(message)s')
logger = logging.getLogger(__name__)

class EventRecorder:
    def __init__(self):
        # Determinar a raiz do projeto mais cedo
        self.script_dir = os.path.dirname(os.path.abspath(__file__)) # .../runescape_ge_automation/core
        self.project_root = os.path.dirname(self.script_dir) # .../runescape_ge_automation

        self.events: List[Dict[str, Any]] = []
        self.start_time: Optional[float] = None
        self.is_recording: bool = False
        self.mouse_listener: Optional[mouse.Listener] = None
        self.keyboard_listener: Optional[keyboard.Listener] = None
        
        self.config = self._load_config() # Agora _load_config pode usar self.project_root
        
        # Rastreamento de movimento do mouse
        self.last_mouse_position: Optional[Tuple[int, int]] = None
        self.last_mouse_time: Optional[float] = None # Timestamp do último evento mouse_move
        
        # Rastreamento de pausa
        self.last_event_time: Optional[float] = None # Timestamp do último evento gravado de qualquer tipo
        self.pause_threshold = self.config.getfloat('Recording', 'pause_threshold', fallback=0.05) 
        self.current_pause_start: Optional[float] = None
        
        # Rastreamento de pressionamento de botão
        self.button_press_times: Dict[str, float] = {}
        
        # Informações da tela
        self.screen_width = 1920 
        self.screen_height = 1080 
        self._initialize_screen_info()
        
        # Rastreamento de ação
        self.current_action: Optional[str] = None
        self.action_start_time: Optional[float] = None
        self.action_events: List[Dict[str, Any]] = []
        
        # Resolver o caminho do suggested_actions_file usando self.project_root
        _suggested_actions_path_config = self.config.get('Paths', 'suggested_actions', fallback='suggested_actions.txt')
        if not os.path.isabs(_suggested_actions_path_config):
            self.suggested_actions_file = os.path.join(self.project_root, _suggested_actions_path_config)
        else:
            self.suggested_actions_file = _suggested_actions_path_config
        logger.info(f"Caminho do arquivo de ações sugeridas resolvido para: {self.suggested_actions_file}")

        self.last_action_check_time = 0.0
        self.action_check_interval = self.config.getfloat('Recording', 'action_check_interval', fallback=0.5)

        # Histórico de movimento para análise de padrões (parece não utilizado no código atual)
        self.movement_history: deque[Dict[str, Any]] = deque(maxlen=self.config.getint('Analysis', 'movement_history_size', fallback=50))
        self.last_direction: Optional[float] = None
        self.micro_adjustments: int = 0
        self.movement_buffer: List[Dict[str, Any]] = [] # Buffer parece não utilizado
        
        self.hotkey_listener_instance: Optional[keyboard.Listener] = None # Instância do listener de hotkeys principal

    def _initialize_screen_info(self) -> None:
        """Inicializa informações da tela para cálculos de movimento relativo."""
        try:
            import pyautogui
            self.screen_width, self.screen_height = pyautogui.size()
            logger.info(f"Tamanho da tela detectado: {self.screen_width}x{self.screen_height}")
        except ImportError:
            logger.warning("pyautogui não encontrado. Usando tamanho de tela padrão 1920x1080. Posições relativas podem ser imprecisas.")
        except Exception as e:
            logger.error(f"Falha ao obter o tamanho da tela usando pyautogui: {str(e)}. Usando padrão.")

    def _load_config(self) -> configparser.ConfigParser:
        """Carrega a configuração do config.ini localizado na raiz do projeto."""
        config = configparser.ConfigParser()
        config_path = os.path.join(self.project_root, 'config.ini') 

        if not os.path.exists(config_path):
            logger.warning(f"Arquivo de configuração não encontrado em {config_path}. Usando valores padrão.")
            config['Paths'] = {'patterns_directory': 'patterns', 'suggested_actions': 'suggested_actions.txt'}
            config['Recording'] = {'pause_threshold': '0.05', 'action_check_interval': '0.5'}
            config['Analysis'] = {'movement_history_size': '50'} # Não utilizado atualmente
            config['Hotkeys'] = {'start_recording': 'Key.f2', 'stop_recording': 'Key.f3'}
            return config
            
        config.read(config_path)
        logger.info(f"Configuração carregada de {config_path}")
        return config

    def _get_time_offset(self) -> int:
        """Calcula o deslocamento de tempo em milissegundos desde o início da gravação."""
        if self.start_time is None:
            return 0
        return int((time.time() - self.start_time) * 1000)

    def _check_for_new_action_from_file(self) -> None:
        """Verifica se há uma nova ação no arquivo suggested_actions.txt."""
        current_time = time.time()
        if current_time - self.last_action_check_time < self.action_check_interval:
            return 
            
        self.last_action_check_time = current_time
        
        try:
            if os.path.exists(self.suggested_actions_file):
                with open(self.suggested_actions_file, 'r', encoding='utf-8') as f: # Adicionado encoding
                    lines = f.readlines()
                    if lines:
                        new_action_line = lines[0].strip()
                        if not new_action_line: 
                            return

                        if new_action_line != self.current_action:
                            logger.info(f"Nova linha de ação detectada: '{new_action_line}'")
                            if self.current_action and self.action_events:
                                logger.info(f"Salvando ação anterior: {self.current_action}")
                                self.save_recording_for_action(self.current_action, self.action_events)
                            
                            self.current_action = new_action_line
                            self.action_start_time = current_time # Usar current_time da verificação
                            self.action_events = [] 
                            logger.info(f"Mundando para nova ação: {self.current_action}")
        except Exception as e:
            logger.error(f"Erro ao verificar novas ações do arquivo: {str(e)}")

    def _parse_action_line(self, action_line: str) -> Tuple[Optional[str], Optional[int]]:
        """Analisa uma linha de ação para extrair o tipo de ação e o ID da caixa opcional."""
        if not action_line:
            return None, None
        try:
            # Remove timestamp potencial como "YYYY-MM-DD HH:MM:SS - "
            if " - " in action_line and action_line.count(':') >= 2: 
                action_line = action_line.split(" - ", 1)[1]
            
            box_id: Optional[int] = None
            action_type_str: str = action_line.strip()

            # Tenta extrair box_id se estiver no formato [id] no final
            if '[' in action_type_str and action_type_str.endswith(']'):
                try:
                    action_name_part = action_type_str[:action_type_str.rfind('[')].strip()
                    box_id_str = action_type_str[action_type_str.rfind('[')+1:-1]
                    box_id = int(box_id_str)
                    action_type_str = action_name_part
                except ValueError: # Se a conversão para int falhar
                    logger.warning(f"Não foi possível analisar box_id da linha de ação: {action_line}. Tratando como parte do nome da ação.")
                    action_type_str = action_line.strip() # Usa a string original como nome da ação
                    box_id = None # Garante que box_id seja None
            
            return action_type_str, box_id
        except Exception as e:
            logger.error(f"Erro ao analisar linha de ação '{action_line}': {str(e)}")
            return action_line.strip(), None # Retorna a linha original como tipo em caso de falha

    def _check_for_pause(self, current_event_time: float) -> None:
        """Verifica se houve uma pausa na atividade e a registra."""
        if self.last_event_time is None: # Primeiro evento, não há pausa para verificar ainda
            self.last_event_time = current_event_time
            return

        time_since_last_event = current_event_time - self.last_event_time
        
        # Se não estivermos em uma pausa e uma pausa deve ter começado
        if time_since_last_event >= self.pause_threshold:
            # Uma pausa ocorreu *antes* deste current_event_time
            pause_start_time = self.last_event_time 
            pause_duration = time_since_last_event # A duração da pausa é o tempo desde o último evento
            
            # Posição no início da pausa
            pause_event_x = self.last_mouse_position[0] if self.last_mouse_position else 0
            pause_event_y = self.last_mouse_position[1] if self.last_mouse_position else 0

            event_data = {
                'type': 'pause',
                'time_offset_ms': int((pause_start_time - self.start_time) * 1000) if self.start_time else 0,
                'duration_ms': int(pause_duration * 1000),
                'x': pause_event_x, 
                'y': pause_event_y
            }
            self.events.append(event_data)
            if self.current_action:
                self.action_events.append(event_data)
            logger.debug(f"Pausa registrada: duração {pause_duration:.3f}s, terminando no offset {event_data['time_offset_ms'] + event_data['duration_ms']}")

        # Atualiza o tempo do último evento para o timestamp do evento atual sendo processado
        self.last_event_time = current_event_time


    def _on_mouse_move(self, x: int, y: int) -> None:
        """Lida com eventos de movimento do mouse, registrando cada ponto com tempo exato."""
        if not self.is_recording or self.start_time is None:
            return

        current_time = time.time()
        self._check_for_pause(current_time) # Verifica se uma pausa terminou com este movimento
        
        # Calcula dt a partir do *evento mouse_move anterior* para tempo de reprodução preciso
        dt = 0.0
        if self.last_mouse_time is not None:
            dt = current_time - self.last_mouse_time
        
        # Métricas básicas de movimento, focando em dt para reprodução
        dx = 0
        dy = 0
        distance = 0.0
        speed = 0.0
        angle = 0.0

        if self.last_mouse_position is not None:
            dx = x - self.last_mouse_position[0]
            dy = y - self.last_mouse_position[1]
            distance = math.sqrt(dx*dx + dy*dy)
            if dt > 0.000001: # Evita divisão por zero ou dt muito pequeno
                speed = distance / dt
            else:
                speed = 0 # Ou um valor grande se distance > 0 e dt for ~0
            angle = math.atan2(dy, dx) * 180 / math.pi
        
        movement_metrics = {
            'dt': dt,  # Delta de tempo desde o ÚLTIMO evento MOUSE MOVE. Crucial para reprodução.
            'distance': distance,
            'speed': speed,
            'angle': angle,
            'dx': dx,
            'dy': dy
        }
        
        event = {
            'type': 'mouse_move',
            'time_offset_ms': self._get_time_offset(), # Deslocamento geral desde o início da gravação
            'x': x,
            'y': y,
            'timestamp': current_time, # Timestamp absoluto deste evento
            'movement_metrics': movement_metrics 
        }
        
        self.events.append(event)
        if self.current_action:
            self.action_events.append(event)

        # Atualiza a última posição e tempo *deste* evento mouse_move
        self.last_mouse_position = (x, y)
        self.last_mouse_time = current_time 

    def _on_mouse_click(self, x: int, y: int, button: mouse.Button, pressed: bool) -> None:
        """Lida com eventos de clique do mouse com tempo preciso."""
        if not self.is_recording or self.start_time is None:
            return
        
        current_time = time.time()
        self._check_for_pause(current_time) # Verifica se uma pausa terminou com este clique

        button_str = str(button)
        event_type = 'mouse_click_press' if pressed else 'mouse_click_release'
        
        event_data: Dict[str, Any] = {
            'type': event_type,
            'time_offset_ms': self._get_time_offset(),
            'x': x,
            'y': y,
            'button': button_str,
            'timestamp': current_time
        }

        if pressed:
            self.button_press_times[button_str] = current_time
        else: # Botão solto
            hold_duration_ms = 0
            if button_str in self.button_press_times:
                hold_duration_ms = int((current_time - self.button_press_times[button_str]) * 1000)
                del self.button_press_times[button_str] # Remove o tempo de pressionamento
            event_data['hold_duration_ms'] = hold_duration_ms
        
        self.events.append(event_data)
        if self.current_action:
            self.action_events.append(event_data)
        
        # Um clique também significa que o mouse está em (x,y) no current_time
        self.last_mouse_position = (x,y) 
        # self.last_mouse_time = current_time # Descomente se cliques devem resetar o cálculo de dt para movimentos subsequentes.
                                            # Mantê-lo comentado significa que dt para um movimento após um clique é do último evento *move*.

    def _on_key_event(self, key_obj: Any, event_type: str) -> None:
        """Manipulador generalizado para pressionar/soltar tecla."""
        if not self.is_recording or self.start_time is None:
            return

        current_time = time.time()
        self._check_for_pause(current_time) # Verifica se uma pausa terminou com este evento de tecla

        try:
            key_str = key_obj.char # Para teclas alfanuméricas
        except AttributeError:
            key_str = str(key_obj) # Para teclas especiais (ex: Key.space, Key.f1)
        
        event_data: Dict[str, Any] = {
            'type': event_type,
            'time_offset_ms': self._get_time_offset(),
            'key': key_str,
            'timestamp': current_time
        }

        if event_type == 'key_press':
            self.button_press_times[key_str] = current_time # Armazena o tempo de pressionamento
        elif event_type == 'key_release':
            hold_duration_ms = 0
            if key_str in self.button_press_times:
                hold_duration_ms = int((current_time - self.button_press_times[key_str]) * 1000)
                del self.button_press_times[key_str] # Remove o tempo de pressionamento
            event_data['hold_duration_ms'] = hold_duration_ms
            
        self.events.append(event_data)
        if self.current_action:
            self.action_events.append(event_data)

    def _on_key_press(self, key: keyboard.Key) -> None:
        self._on_key_event(key, 'key_press')

    def _on_key_release(self, key: keyboard.Key) -> None:
        self._on_key_event(key, 'key_release')

    def _handle_hotkey_press(self, key: Any) -> None:
        """Lida com pressionamentos de hotkey (executa na thread do listener de hotkeys)."""
        start_hotkey_str = self.config.get('Hotkeys', 'start_recording', fallback='Key.f2')
        stop_hotkey_str = self.config.get('Hotkeys', 'stop_recording', fallback='Key.f3')

        key_pressed_str = ""
        if isinstance(key, keyboard.Key): # Teclas especiais
            key_pressed_str = str(key) 
        elif isinstance(key, keyboard.KeyCode): # Teclas alfanuméricas
            if key.char:
                key_pressed_str = key.char # Pode precisar de formatação como "'c'" dependendo da config

        # Normalizar a string da tecla pressionada para comparação (ex: remover aspas de caracteres)
        if key_pressed_str.startswith("'") and key_pressed_str.endswith("'") and len(key_pressed_str) == 3:
            key_pressed_str = key_pressed_str[1]

        # logger.debug(f"Hotkey pressed: {key_pressed_str}, Start: {start_hotkey_str}, Stop: {stop_hotkey_str}")

        if key_pressed_str == start_hotkey_str:
            if not self.is_recording:
                logger.info(f"Hotkey '{start_hotkey_str}' pressionada - Iniciando gravação")
                self.start_recording()
            else:
                logger.info(f"Hotkey '{start_hotkey_str}' pressionada, mas já gravando.")
        elif key_pressed_str == stop_hotkey_str:
            if self.is_recording:
                logger.info(f"Hotkey '{stop_hotkey_str}' pressionada - Parando gravação")
                self.stop_recording() # Isso agora também tentará parar o hotkey_listener_instance
            else:
                logger.info(f"Hotkey '{stop_hotkey_str}' pressionada, mas não gravando.")


    def start_recording(self) -> None:
        """Inicia a gravação de eventos de mouse e teclado."""
        if self.is_recording:
            logger.warning("A gravação já está em progresso")
            return

        self.events = []
        self.action_events = [] 
        self.start_time = time.time()
        self.is_recording = True
        
        # Reseta estados
        self.last_mouse_position = None
        self.last_mouse_time = None # Crucial para cálculo de dt
        self.last_event_time = self.start_time # Inicializa para detecção de pausa
        self.current_pause_start = None
        self.button_press_times = {}
        
        # Manipulação de ação
        self.action_start_time = self.start_time # Ou o tempo da primeira ação do arquivo
        self.last_action_check_time = self.start_time # Reseta timer de verificação de ação

        self.current_action = None # Reseta ação atual
        self._check_for_new_action_from_file() # Tenta carregar ação inicial
        if not self.current_action:
            logger.info("Nenhuma ação inicial especificada em suggested_actions.txt. Gravação será geral.")

        # Inicia listener de mouse
        self.mouse_listener = mouse.Listener(
            on_move=self._on_mouse_move,
            on_click=self._on_mouse_click
            # on_scroll=self._on_mouse_scroll # Adicionar se eventos de rolagem forem necessários
        )
        self.mouse_listener.start()

        # Inicia listener de teclado
        self.keyboard_listener = keyboard.Listener(
            on_press=self._on_key_press,
            on_release=self._on_key_release
        )
        self.keyboard_listener.start()

        logger.info("Gravação de eventos iniciada.")

    def stop_recording(self) -> None:
        """Para a gravação de eventos e limpa os listeners."""
        if not self.is_recording:
            logger.warning("Nenhuma gravação em progresso para parar.")
            return

        logger.info("Iniciando processo de parada da gravação...")
        self.is_recording = False # Define isso primeiro para parar callbacks de processamento
        
        # Para listeners de dados
        if self.mouse_listener:
            logger.debug("Parando listener de mouse...")
            self.mouse_listener.stop()
            self.mouse_listener.join() 
            self.mouse_listener = None
            logger.debug("Listener de mouse parado.")
        
        if self.keyboard_listener:
            logger.debug("Parando listener de teclado (dados)...")
            self.keyboard_listener.stop()
            self.keyboard_listener.join() 
            self.keyboard_listener = None
            logger.debug("Listener de teclado (dados) parado.")

        # Registra pausa final se houver
        if self.last_event_time and self.start_time: 
            current_time = time.time()
            # Verifica se houve tempo desde o último evento para considerar uma pausa
            if current_time > self.last_event_time + self.pause_threshold : 
                 self._check_for_pause(current_time) # Processa pausa final potencial

        # Salva a gravação para a ação atual
        if self.current_action and self.action_events:
            logger.info(f"Salvando ação final: {self.current_action} com {len(self.action_events)} eventos.")
            self.save_recording_for_action(self.current_action, self.action_events)
        elif not self.current_action and self.events: # Nenhuma ação específica, salva todos os eventos
            logger.info(f"Nenhum nome de ação específico. Salvando todos os {len(self.events)} eventos gravados com nome genérico.")
            generic_action_name = f"recording_{datetime.now().strftime('%Y%m%d_%H%M%S')}"
            self.save_recording_for_action(generic_action_name, self.events)
        else:
            logger.info("Nenhum evento gravado para a ação atual ou nenhuma ação especificada.")
            
        logger.info(f"Gravação parada. Total de eventos capturados em self.events: {len(self.events)}")

        # Tenta parar o listener de hotkeys principal
        if self.hotkey_listener_instance:
            logger.info("Tentando parar o listener de hotkeys principal...")
            self.hotkey_listener_instance.stop()
            # Não chamamos join() aqui, pois o join() está no run_hotkey_listener

    def save_recording_for_action(self, action_name_line: str, events_to_save: List[Dict[str, Any]]) -> Optional[str]:
        """
        Salva os eventos fornecidos em um arquivo JSON para a linha de nome de ação especificada.
        Usa self.project_root para resolver patterns_directory relativo.
        """
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
            logger.debug(f"Diretório de padrões: {abs_patterns_dir}")

            action_type, box_id = self._parse_action_line(action_name_line)
            if not action_type: # Fallback se _parse_action_line retornar None para action_type
                action_type = "unknown_action" 
                logger.warning(f"Não foi possível analisar a linha de ação '{action_name_line}', usando '{action_type}'.")

            # Cria uma base de nome de arquivo segura
            safe_action_filename_base = "".join(c if c.isalnum() or c in ('_','-') else '_' for c in action_type)
            if box_id is not None:
                safe_action_filename_base = f"{safe_action_filename_base}_box{box_id}"

            timestamp_str = datetime.now().strftime("%Y%m%d_%H%M%S_%f") # Adicionado microssegundos para singularidade
            filename = f"{safe_action_filename_base}_{timestamp_str}.json"
            filepath = os.path.join(abs_patterns_dir, filename)
            
            logger.info(f"Tentando salvar em: {filepath}")

            recording_data = {
                'action_name_line': action_name_line, # Linha original do arquivo
                'parsed_action_type': action_type,
                'parsed_box_id': box_id,
                'save_timestamp': datetime.now().isoformat(),
                'total_events': len(events_to_save),
                'events': events_to_save # Salva a lista de eventos específica da ação
            }
            
            with open(filepath, 'w', encoding='utf-8') as f: # Adicionado encoding
                json.dump(recording_data, f, indent=2, ensure_ascii=False) # ensure_ascii=False para caracteres non-ASCII
            
            logger.info(f"Salvos {len(events_to_save)} eventos com sucesso em: {filepath}")
            return filepath
        except Exception as e:
            logger.error(f"Falha ao salvar gravação para ação '{action_name_line}': {str(e)}")
            import traceback
            logger.error(traceback.format_exc())
            return None

    def get_events(self) -> List[Dict[str, Any]]:
        """Obtém a lista de todos os eventos gravados (lista mestre)."""
        return self.events.copy()

    def run_hotkey_listener(self) -> None:
        """Executa o listener de hotkeys na thread atual. Bloqueante."""
        logger.info("Listener de hotkeys iniciado. Pressione as hotkeys configuradas (ex: F2 para iniciar, F3 para parar).")
        
        action_check_active = True
        action_check_thread = None

        def _periodic_action_check():
            while action_check_active:
                if self.is_recording:
                    self._check_for_new_action_from_file()
                time.sleep(self.action_check_interval) # Usa o intervalo configurado
            logger.debug("Thread de verificação de ação periódica terminando.")

        try:
            # Inicia a thread de verificação de ação periódica
            import threading
            action_check_thread = threading.Thread(target=_periodic_action_check, daemon=True)
            action_check_thread.start()

            # O listener de hotkeys é gerenciado pelo 'with' statement
            with keyboard.Listener(on_press=self._handle_hotkey_press) as listener:
                self.hotkey_listener_instance = listener # Armazena a instância para parada externa
                logger.debug(f"Listener de hotkeys ({type(listener)}) atribuído a self.hotkey_listener_instance")
                listener.join() # Bloqueia até que o listener de hotkeys seja parado

        except KeyboardInterrupt:
            logger.info("Interrupção de teclado (Ctrl+C) recebida. Parando gravador...")
            if self.is_recording:
                self.stop_recording() 
            # O 'with' statement para o listener de hotkeys cuidará de pará-lo.
        except Exception as e:
            logger.error(f"Erro inesperado no listener de hotkeys: {e}", exc_info=True)
            if self.is_recording:
                self.stop_recording()
        finally:
            logger.info("Bloco finally do run_hotkey_listener alcançado.")
            action_check_active = False # Sinaliza a thread de verificação para parar
            if action_check_thread and action_check_thread.is_alive():
                logger.debug("Aguardando a thread de verificação de ação periódica terminar...")
                action_check_thread.join(timeout=self.action_check_interval * 2 + 0.1) # Timeout um pouco maior
                if action_check_thread.is_alive():
                    logger.warning("Thread de verificação de ação periódica não terminou a tempo.")
            
            if self.hotkey_listener_instance and self.hotkey_listener_instance.running:
                 logger.info("Listener de hotkeys ainda está rodando no finally, tentando parar explicitamente.")
                 self.hotkey_listener_instance.stop() # Garante que seja parado se ainda estiver rodando

            self.hotkey_listener_instance = None # Limpa a referência
            logger.info("Listener de hotkeys e thread de verificação de ação finalizados.")


    def main_loop(self) -> None: # Mantido para modelo de execução alternativo potencial
        """Loop operacional principal para o gravador."""
        logger.info("Loop principal do gravador iniciado. Gerencie a gravação via métodos start/stop ou integre hotkeys.")
        try:
            while True: 
                if self.is_recording: 
                    self._check_for_new_action_from_file() 
                time.sleep(self.action_check_interval / 2) # Dorme um pouco
        except KeyboardInterrupt:
            logger.info("Loop principal do gravador interrompido pelo usuário (Ctrl+C).")
        finally:
            if self.is_recording:
                logger.info("Parando gravação devido à terminação do loop principal...")
                self.stop_recording()
            # Se hotkey_listener_instance foi usado por outro mecanismo, pode precisar ser parado aqui.
            # No entanto, main_loop e run_hotkey_listener são geralmente mutuamente exclusivos.
            if self.hotkey_listener_instance and self.hotkey_listener_instance.running:
                 logger.info("Parando listener de hotkeys do main_loop.")
                 self.hotkey_listener_instance.stop()
            logger.info("Loop principal do gravador finalizado.")


if __name__ == "__main__":
    recorder = EventRecorder()
    
    logger.info("Iniciando EventRecorder com suporte a hotkey (F2 para iniciar, F3 para parar por padrão).")
    logger.info(f"Arquivo de configuração esperado em: {os.path.join(recorder.project_root, 'config.ini')}")
    logger.info(f"Arquivo de ações sugeridas: {recorder.suggested_actions_file}") 
    
    patterns_dir_config_val = recorder.config.get('Paths', 'patterns_directory', fallback='patterns')
    if not os.path.isabs(patterns_dir_config_val):
        resolved_patterns_dir = os.path.join(recorder.project_root, patterns_dir_config_val)
    else:
        resolved_patterns_dir = patterns_dir_config_val
    logger.info(f"Diretório de padrões: {resolved_patterns_dir}")

    recorder.run_hotkey_listener()
    logger.info("Programa EventRecorder encerrado.")
