import socket
import pandas as pd
pd.set_option('display.max_columns', None)
import numpy as np
from scipy.spatial import KDTree
from io import BytesIO
import threading
import queue
import time
import zmq

def load_data():
    global top_position_data
    global bottom_position_data
    global top_shot_data
    global bottom_shot_data
    global top_position_kd
    global bottom_position_kd 
    global top_shot_kd
    global bottom_shot_kd
    # Specify the path to your Excel file
    excel_file_path = 'data.xlsx'

    # Read the Excel file into a Pandas DataFrame
    data = pd.read_excel(excel_file_path)
    columns_to_drop = ['Unnamed: 0', 'frame', 'time', 'role1', 'role2', 'role3', 'role4', 'fromx' , 'fromy' ,'duration', 'shot_full', 'rally']
    data = data.drop(columns=columns_to_drop)
    data.to_excel('nombre_del_archivo.xlsx', index=False)
    
    # Filter data by column
    # Top position data -> 'last hit' == 'T'
    top_position_data = data[data['lastHit'] == 'T']
    # Bot position data -> 'last hit' == 'B'
    bottom_position_data = data[data['lastHit'] == 'B']
    # Top shot data -> shots from 'T'
    top_shot_data = top_position_data[top_position_data['shot'] != 'undef']
    # Top shot data -> shots from 'B'
    bottom_shot_data = bottom_position_data[bottom_position_data['shot'] != 'undef']

    # Transform data to numpy arrays
    top_position_data = top_position_data.values
    bottom_position_data = bottom_position_data.values
    top_shot_data = top_shot_data.values
    bottom_shot_data = bottom_shot_data.values

    # Create the corresponding KD-Trees
    top_position_kd = KDTree(top_position_data[:, 0:10])
    bottom_position_kd = KDTree(bottom_position_data[:, 0:10])
    top_shot_kd = KDTree(top_shot_data[:,0:10])
    bottom_shot_kd = KDTree(bottom_shot_data[:,0:10])

def process_shot_request(command_array):
    player_id = command_array[1]
    query_array = np.array([float(value.replace(',', '.')) for value in command_array[2:]]).astype(float)
    if (player_id == 'T1_1' or player_id == 'T1_2'):
        dist, index = bottom_shot_kd.query(query_array)
        return bottom_shot_data[index, 18:21]
    else:
        dist, index = top_shot_kd.query(query_array)
        return top_shot_data[index, 18:21]

def process_movement_request(command_array):
    player_id = command_array[1]
    lastHitByTeam = command_array[-1]
    query_array = np.array([float(value.replace(',', '.')) for value in command_array[2:-1]]).astype(float)
    if (lastHitByTeam == 'T1'):
        dist, index = top_position_kd.query(query_array)
        return np.concatenate((top_position_data[index, 0:8], top_position_data[index, 10:18]), axis=None)
    else:
        dist, index = bottom_position_kd.query(query_array)
        return np.concatenate((bottom_position_data[index, 0:8], bottom_position_data[index, 10:18]), axis=None)
    

def process_command(command):
    command_array = command.split()
    command_type = command_array[0]

    if command_type == 'SHOT_REQUEST':
        start_time = time.time()
        nearest_sample = process_shot_request(command_array)
        elapsed_time = time.time() - start_time
        response = "SHOT_RESPONSE " + command_array[1] + ' ' + ' '.join(str(value) for value in nearest_sample) 
        print("SENDING SHOT RESPONSE: " + response)
        print(f"Elapsed time: {elapsed_time} seconds")
        response_socket.send_string(response)
    elif command_type == 'MOVEMENT_REQUEST':
        start_time = time.time()
        nearest_sample = process_movement_request(command_array)
        elapsed_time = time.time() - start_time
        response = "MOVEMENT_RESPONSE " + command_array[1] + ' ' + ' '.join(str(value) for value in nearest_sample)
        print("SENDING MOVEMENT RESPONSE: " + response)
        print(f"Elapsed time: {elapsed_time} seconds")
        response_socket.send_string(response)

def command_handler():
    print("HANDLING COMMANDS")
    while True:
        try:
            command = command_queue.get(timeout=1)  # Check the queue for new commands
            process_command(command)
        except queue.Empty:
            pass

def handle_client():
    global command_socket
    global response_socket
    context = zmq.Context()

    command_socket = context.socket(zmq.PULL)
    command_socket.bind("tcp://127.0.0.1:5555")

    response_socket = context.socket(zmq.PUB)
    response_socket.bind("tcp://127.0.0.1:5556")
    print("Connected to Unity")

    while True:
        print("Waiting for command...")
        try:
            command = command_socket.recv_string()  # Receive the command from Unity
            print(f"Received command: {command}")
            commands = command.split("\n")
            for cmd in commands:
                if cmd:
                    command_queue.put(cmd)
        except zmq.error.ZMQError as e:
            print(f"ZMQError occurred: {e}")
        except Exception as e:
            print(f"An unexpected error occurred: {e}")
            break

    print("Connection to Unity closed")
    command_socket.close()  # Ensure the socket is closed
    response_socket.close()
    context.term()  # Terminate the context

if __name__ == "__main__":
    global command_queue
    command_queue = queue.Queue()
    load_data()

    # Iniciar el hilo para recibir comandos de Unity
    client_thread = threading.Thread(target=handle_client)
    client_thread.daemon = True
    client_thread.start()

    # Iniciar el hilo para manejar comandos
    handle_thread = threading.Thread(target=command_handler)
    handle_thread.daemon = True
    handle_thread.start()

    # Mantener el hilo principal vivo
    client_thread.join()
    handle_thread.join()


