import sys
import time # Usado para time.time() para registrar timestamps
from PyQt5.QtWidgets import QApplication, QMainWindow, QWidget, QVBoxLayout, QPushButton, QLabel
from PyQt5.QtGui import QPainter, QPen, QColor, QPainterPath
from PyQt5.QtCore import Qt, QPoint, QTimer

class DrawingWindow(QWidget):
    def __init__(self):
        super().__init__()
        self.setWindowTitle("Mouse Movement Test")
        self.setGeometry(100, 100, 800, 600)
        self.setStyleSheet("background-color: white;")
        
        # Estado do desenho
        self.drawing_active = False  # Verdadeiro quando o botão do mouse está pressionado
        self.live_points = []      # Pontos para o desenho ao vivo atual
        
        # Estado da reprodução
        self.replayed_points = []    # Pontos para exibir durante a reprodução
        self.events_to_replay = []   # Eventos capturados para reprodução
        self.current_replay_idx = 0
        self.is_replaying = False

        # Timer para a reprodução
        self.replay_timer = QTimer(self)
        self.replay_timer.timeout.connect(self.process_next_replay_step)

        # Para registrar o tempo dos eventos
        self.last_event_time = None

    def paintEvent(self, event):
        painter = QPainter(self)
        painter.setRenderHint(QPainter.Antialiasing) # Linhas mais suaves
        # Caneta para o desenho
        pen = QPen(QColor(0,0,0), 2, Qt.SolidLine, Qt.RoundCap, Qt.RoundJoin)
        painter.setPen(pen)
        
        # Determina qual conjunto de pontos desenhar
        points_to_draw = self.replayed_points if self.is_replaying else self.live_points
        
        if len(points_to_draw) > 1:
            path = QPainterPath()
            path.moveTo(points_to_draw[0])
            for i in range(1, len(points_to_draw)):
                path.lineTo(points_to_draw[i])
            painter.drawPath(path)

    def mousePressEvent(self, event):
        # Inicia o desenho se o botão esquerdo for pressionado e não estiver reproduzindo
        if event.button() == Qt.LeftButton and not self.is_replaying:
            self.drawing_active = True
            self.live_points = [event.pos()] # Começa uma nova linha
            
            self.events_to_replay = [] # Limpa a gravação anterior
            self.last_event_time = time.time() # Registra o tempo do primeiro ponto
            
            # Grava o primeiro ponto. 'dt' é 0 para o primeiro ponto.
            self.events_to_replay.append({
                'x': event.pos().x(), 
                'y': event.pos().y(), 
                'dt': 0.0 
            })
            self.update() # Solicita redesenho

    def mouseMoveEvent(self, event):
        # Continua o desenho se ativo e o mouse se mover
        if self.drawing_active and not self.is_replaying:
            self.live_points.append(event.pos())
            
            current_time = time.time()
            # Calcula o tempo delta desde o último evento gravado
            dt = current_time - self.last_event_time
            self.last_event_time = current_time # Atualiza o tempo do último evento
            
            # Grava o ponto atual e o tempo delta
            self.events_to_replay.append({
                'x': event.pos().x(), 
                'y': event.pos().y(), 
                'dt': dt 
            })
            self.update() # Solicita redesenho

    def mouseReleaseEvent(self, event):
        # Finaliza o desenho se o botão esquerdo for solto
        if event.button() == Qt.LeftButton and self.drawing_active:
            self.drawing_active = False
            if self.events_to_replay and len(self.events_to_replay) > 1: # Precisa de pelo menos 2 pontos (press + move)
                print(f"Desenho gravado: {len(self.events_to_replay)} pontos.")
                # Inicia a reprodução após um pequeno atraso (1 segundo)
                QTimer.singleShot(1000, self.start_replay_drawing)
            else:
                print("Nenhum desenho significativo gravado.")
                self.events_to_replay = [] # Limpa se não for significativo


    def start_replay_drawing(self):
        # Inicia o processo de reprodução
        if not self.events_to_replay:
            print("Nenhum evento para reproduzir.")
            return

        self.is_replaying = True
        self.live_points = []       # Limpa o display de desenho ao vivo
        self.replayed_points = []   # Limpa a reprodução anterior
        self.current_replay_idx = 0
        self.update() # Limpa o conteúdo da janela antes de iniciar a reprodução

        # Processa o primeiro ponto da reprodução imediatamente
        # O QTimer será usado para os pontos subsequentes com base no 'dt'
        self.process_next_replay_step()


    def process_next_replay_step(self):
        # Processa cada etapa da reprodução
        if self.current_replay_idx < len(self.events_to_replay):
            event_data = self.events_to_replay[self.current_replay_idx]
            
            self.replayed_points.append(QPoint(event_data['x'], event_data['y']))
            self.update() # Redesenha com o novo ponto
            
            self.current_replay_idx += 1 # Move para o próximo evento
            
            if self.current_replay_idx < len(self.events_to_replay):
                # Se houver mais eventos, agenda o próximo passo
                # O 'dt' do *próximo* evento determina o atraso
                next_event_data = self.events_to_replay[self.current_replay_idx]
                delay_ms = int(next_event_data['dt'] * 1000)
                # Garante um delay mínimo para o timer não ser 0, o que pode causar problemas.
                # Um dt muito pequeno pode ainda ser rápido demais visualmente.
                if delay_ms < 10: delay_ms = 10 # Delay mínimo de 10ms para visibilidade
                self.replay_timer.start(delay_ms)
            else:
                # Reprodução finalizada
                self.finalize_replay()
        else:
            # Reprodução finalizada (caso seja chamado novamente sem eventos)
            self.finalize_replay()

    def finalize_replay(self):
        # Chamado quando a reprodução termina
        self.replay_timer.stop()
        self.is_replaying = False
        print("Reprodução finalizada.")
        # Opcional: limpar events_to_replay ou preparar para novo desenho automaticamente
        # self.events_to_replay = [] 

    def reset_internal_state(self):
        """Redefine o estado da janela de desenho."""
        self.drawing_active = False
        self.is_replaying = False
        self.replay_timer.stop()
        self.live_points = []
        self.replayed_points = []
        self.events_to_replay = []
        self.current_replay_idx = 0
        self.last_event_time = None
        self.update() # Limpa a tela
        print("Janela de desenho redefinida.")

class MainWindow(QMainWindow):
    def __init__(self):
        super().__init__()
        self.setWindowTitle("Teste de Replay de Movimento do Mouse")
        self.setGeometry(100, 100, 850, 700) # Janela um pouco maior
        
        central_widget = QWidget()
        self.setCentralWidget(central_widget)
        layout = QVBoxLayout(central_widget)
        
        instructions = QLabel(
            "Desenhe algo com o mouse na área branca abaixo.\n"
            "O movimento (caminho e tempo) será reproduzido após você soltar o botão do mouse."
        )
        instructions.setAlignment(Qt.AlignCenter)
        layout.addWidget(instructions)
        
        self.drawing_window = DrawingWindow()
        layout.addWidget(self.drawing_window)
        
        reset_button = QPushButton("Redefinir Desenho / Novo Desenho")
        reset_button.clicked.connect(self.reset_drawing_action)
        layout.addWidget(reset_button)
        
    def reset_drawing_action(self):
        # Chama o método de reset da janela de desenho
        self.drawing_window.reset_internal_state()

    def closeEvent(self, event):
        """Garante que os timers sejam parados se a janela for fechada."""
        if hasattr(self, 'drawing_window') and self.drawing_window.replay_timer.isActive():
            self.drawing_window.replay_timer.stop()
        event.accept()

if __name__ == "__main__":
    app = QApplication(sys.argv)
    window = MainWindow()
    window.show()
    sys.exit(app.exec_())
