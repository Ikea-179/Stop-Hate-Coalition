import datetime
import numpy as np
import os

import torch

import pandas as pd
import seaborn as sns
import matplotlib.pyplot as plt

from sklearn.metrics import accuracy_score
from sklearn.metrics import f1_score
from sklearn.metrics import mean_squared_error
from sklearn.metrics import classification_report
from sklearn.metrics import confusion_matrix
''' 
from models.BasicLSTM import BasicLSTM
from models.BiLSTM import BiLSTM
from models.Transformers import DistillBert, DistillBertEmotion
from models.Hybrid_CNN_LSTM import Hybrid_CNN_LSTM, Hybrid_LSTM_CNN, AutoTransformer, PyramidCNN
from models.Hybrid_LSTM_CNN import Hybrid_LSTM_CNN, AutoTransformer, PyramidCNN
from models.AutoTransformer import AutoTransformer, PyramidCNN
from models.PyramidCNN import PyramidCNN'''

#import models
#from models import BasicLSTM
import utils.models.BasicLSTM as BasicLSTM
import utils.models.BiLSTM as BiLSTM
import utils.models.Transformers as Transformers
import utils.models.Hybrid_CNN_LSTM as Hybrid_CNN_LSTM
import utils.models.Hybrid_LSTM_CNN as Hybrid_LSTM_CNN
import utils.models.AutoTransformer as AutoTransformer
import utils.models.PyramidCNN as PyramidCNN

SAVED_MODELS_PATH = "saved-models/"
FIGURES_PATH = "figures/"
GRIDSEARCH_CSV = "gridsearch-results/"
STATS_CSV = "stats-results/"

def load_model(model_type, field, device, fix_length=None):
    """
    Load and return model.
    """
    if model_type == 'BasicLSTM':
        model = BasicLSTM.BasicLSTM(dim_emb=300, num_words=field.vocab.__len__(), 
                                    hidden_dim=128, num_layers=2, output_dim=1)

    elif model_type == 'BiLSTM':
        model = BiLSTM.BiLSTM(dim_emb=300, num_words=field.vocab.__len__(), 
                                    hidden_dim=128, num_layers=2, output_dim=1)
    elif model_type == 'Transformers':
        model = Transformers.Transformers(dim_emb=128, num_words=field.vocab.__len__(), 
                                          hidden_dim=128, num_layers=2, output_dim=1)
    elif model_type == 'TinyBert':
        model = AutoTransformer.AutoTransformer(dim_emb=128, num_words=field.vocab.__len__(), 
                                          hidden_dim=128, num_layers=2, output_dim=1, hidden_dropout_prob = 0.5)
    elif model_type == 'DistillBert':
        model = Transformers.DistillBert()

    elif model_type == 'DistillBertEmotion':
        model = Transformers.DistillBertEmotion()

    elif model_type == 'HybridCNNLSTM':
	      model = Hybrid_CNN_LSTM.HybridCNNLSTM()
        
    elif model_type == 'HybridLSTMCNN':
	      model = Hybrid_LSTM_CNN.HybridLSTMCNN(fix_length=fix_length)
        

    else:
        model = None
    model.to(device)

    return model

def load_trained_model(model, saved_model_path, device):
    """
    Load and return trained model. Initialize the model first with load_model().
    """
    model.load_state_dict(torch.load(saved_model_path, map_location=device))
    print(f"{saved_model_path} loaded.")
    model.to(device)

    return model

def save_model(model, hist, model_type, do_save, do_print=False):
    """
    Save the trained model.
    """
    if do_save:
        end_time = hist['end_time']
        saved_model_path = f"{SAVED_MODELS_PATH}{model_type}_{end_time}_trained_testAcc={hist['test_acc']}.pth"
        torch.save(model.state_dict(), saved_model_path)
        if do_print: print(f"Model saved at {saved_model_path}")

def plot_training(hist, model_type, do_save, do_plot=False, do_print=False):
    """
    Plot the training and validation loss/accuracy.
    """

    if not os.path.exists('figures'):
        os.makedirs('figures')

    fig, ax = plt.subplots(1, 2, figsize=(15,5))
    ax[0].set_title(f'{model_type} - loss')
    ax[0].plot(hist["epochs"], hist["train_loss"], label="Train loss")
    ax[0].plot(hist["epochs"], hist["val_loss"], label="Validation loss")
    ax[1].set_title(f'{model_type} - accuracy')
    ax[1].plot(hist["epochs"], hist["train_acc"], label="Train accuracy")
    ax[1].plot(hist["epochs"], hist["val_acc"], label="Validation accuracy")
    ax[0].legend()
    ax[1].legend()
    if do_save:
        end_time = hist['end_time']
        save_graph_path = f"{FIGURES_PATH}{model_type}_losses&acc_{end_time}_testAcc={hist['test_acc']}.png"
        plt.savefig(save_graph_path)
        if do_print: print(f"Training graph saved at {save_graph_path}")
    if do_plot: plt.show()

def classif_report(hist, list_names=[]):
    """
    Give the classification report from sklearn.
    """
    y_pred = [y for y in hist['y_pred']]
    y_true = [y for y in hist['y_true']]

    nb_classes = len(set(y_true))

    accuracy = round(accuracy_score(y_true, y_pred)*100, 3)
    macro_f1score = round(f1_score(y_true, y_pred, average='macro')*100, 3)
    binary_f1score = round(f1_score(y_true, y_pred, average='binary')*100, 3)
    mse = round(mean_squared_error(y_true, y_pred), 3)
    print(f'Accuracy: {accuracy}%')
    print(f'Macro F1-score: {macro_f1score}%')
    print(f'Binary F1-score: {binary_f1score}%')
    print(f'MSE: {mse}')
    target_names = list_names if list_names else [f'class {i}' for i in range(nb_classes)]
    print(classification_report(y_true, y_pred, target_names=target_names))

def plot_cm(hist, model_type, do_save, do_plot=False, do_print=False):
    """
    Plot the confusion matrix after testing.
    """

    if not os.path.exists('figures'):
        os.makedirs('figures')

    y_pred = [y for y in hist['y_pred']]
    y_true = [y for y in hist['y_true']]

    nb_classes = len(set(y_true))
    end_time = hist['end_time']
    cm_path = f"{FIGURES_PATH}{model_type}_CM_{end_time}_testAcc={hist['test_acc']}.png"

    cm = confusion_matrix(y_true, y_pred)
    df_cm = pd.DataFrame(cm, index = [i for i in range(nb_classes)], 
                         columns = [i for i in range(nb_classes)])
    plt.figure(figsize = (10,7))
    cmap = sns.cubehelix_palette(light=1, as_cmap=True)
    sns.heatmap(df_cm, cmap=cmap, annot=True, fmt='.0f')
    plt.title(f"Confusion Matrix for {model_type}")

    if do_save:
        plt.savefig(cm_path)
        if do_print: print(f"Confusion Matrix saved at {cm_path}")
    if do_plot: plt.show()