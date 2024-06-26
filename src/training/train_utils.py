import time
import numpy as np
import os

import tqdm
import copy

import torch
import torch.nn as nn

from sklearn.metrics import f1_score

from utils.utils import SAVED_MODELS_PATH

def train_model(model, criterion, optimizer, dataloaders, history_training, 
                scheduler=None, num_epochs=10, patience_es=5, training_remaining=1,
                save_condition='acc'):
    '''
    Main training function
    '''
    print("\n**TRAINING**\n")
    # Init Early stoping class
    early_stopping = EarlyStopping(patience=patience_es, verbose=False, delta=0, save_condition=save_condition)

    since = time.time()
    best_model_wts = copy.deepcopy(model.state_dict())
    best_val_acc = 0.0
    min_val_loss = float('inf')

    history_training['epochs'] = np.arange(num_epochs)
    history_training['best_epoch'] = num_epochs - 1
    loss_criterion = history_training['loss_criterion']
    scheduler_type = history_training['scheduler_type']

    # Iterate over epochs.
    for epoch in range(num_epochs):
        lasttime = time.time()
        print('Epoch {}/{} | Trainings remaining: {}'.format(epoch, num_epochs - 1, training_remaining))
        print('-' * 10)
        current_lr = optimizer.state_dict()['param_groups'][0]['lr']
        print('current lr:', current_lr)

        # Each epoch has a training and validation phase
        for phase in ['train', 'val']:
            if phase == 'train':
                model.train()  # Set model to training mode
            else:
                model.eval()   # Set model to evaluate mode

            running_loss = 0.0
            preds_list = []
            labels_list = []

            nb_batches = len(dataloaders[phase])
            length_phase = len(dataloaders[phase].dataset)

            # Iterate over data.
            pbar = tqdm.tqdm([i for i in range(nb_batches)])

            for batch_idx, (inputs, labels) in enumerate(dataloaders[phase]):
                pbar.update()
                pbar.set_description("Processing batch %s" % str(batch_idx+1))
                if loss_criterion in ['bceloss', 'bcelosswithlogits']:
                    labels = labels.float()

                # zero the parameter gradients
                optimizer.zero_grad()

                # forward
                # track history if only in train
                with torch.set_grad_enabled(phase == 'train'):
                    outputs = model.forward(inputs)
                    loss = criterion(outputs, labels)

                    # backward + optimize only if in training phase
                    if phase == 'train':
                        loss.backward()
                        optimizer.step()
                        if scheduler_type == 'linear_schedule_with_warmup':
                            scheduler.step()

                # statistics
                running_loss += loss.item() * inputs.size(1)
                if loss_criterion in ['bceloss', 'bcelosswithlogits']:
                    preds = torch.where(outputs > 0.5, 1, 0).tolist()
                else:
                    preds = torch.argmax(outputs, 1).tolist()
                preds_list += preds
                labels_list += labels.tolist()

            pbar.close()

            epoch_loss = running_loss / length_phase
            epoch_acc = f1_score(labels_list, preds_list, average='macro')

            print('{} Loss: {:.4f} Acc: {:.4f}'.format(
                phase, epoch_loss, epoch_acc))            

            history_training[f'{phase}_loss'].append(epoch_loss)
            history_training[f'{phase}_acc'].append(epoch_acc)

            # deep copy the model
            if phase == 'val':
                valid_loss = None
                valid_acc = None
                if scheduler_type == 'reduce_lr_on_plateau' and epoch != 0:
                    scheduler.step(history_training['val_loss'][-1])

                if save_condition == 'acc':
                    valid_acc = epoch_acc # Register validation acc for Early Stopping
                    if epoch_acc >= best_val_acc:
                        best_val_acc = epoch_acc
                        history_training['best_epoch'] = epoch
                        best_model_wts = copy.deepcopy(model.state_dict())
                else:
                    valid_loss = epoch_loss # Register validation loss for Early Stopping
                    if epoch_loss <= min_val_loss:
                        min_val_loss = epoch_loss
                        history_training['best_epoch'] = epoch
                        best_model_wts = copy.deepcopy(model.state_dict())

        print("Epoch complete in {:.1f}s\n".format(time.time() - lasttime))

        # Check Early Stopping
        early_stopping(valid_loss, valid_acc, model)

        if early_stopping.early_stop:
            print("Early stopping")
            history_training['epochs'] = np.arange(epoch + 1)
            break

    time_elapsed = time.time() - since
    print('Training complete in {:.0f}m {:.0f}s'.format(
        time_elapsed // 60, time_elapsed % 60))
    best_val_acc = history_training['val_acc'][history_training['best_epoch']]
    best_val_acc = round(float(best_val_acc), 4)
    print('Best val Acc: {:4f}'.format(best_val_acc))

    # Load best model weights
    model.load_state_dict(best_model_wts)

    return (model, history_training)

def test_model(model, history_training, dataloaders):
    """
    Testing function. 
    Print the loss and accuracy after the inference on the testset.
    """
    print("\n\n**TESTING**\n")

    start_time = time.time()

    phase = "test"
    model.eval()

    running_loss = 0.0
    preds_list = []
    labels_list = []

    nb_batches = len(dataloaders[phase])
    length_phase = len(dataloaders[phase].dataset)
    loss_criterion = history_training['loss_criterion']
    if loss_criterion == 'bceloss':
        criterion = nn.BCELoss()
    elif loss_criterion == 'bcelosswithlogits':
        criterion = nn.BCEWithLogitsLoss()
    elif loss_criterion == 'crossentropy':
        criterion = nn.CrossEntropyLoss()
    else: # Default to BCEWithLogitsLoss
        criterion = nn.BCEWithLogitsLoss()
    print('Loss used: {}'.format(criterion))

    pbar = tqdm.tqdm([i for i in range(nb_batches)])

    # Iterate over data.
    for batch_idx, (inputs, labels) in enumerate(dataloaders[phase]):
        pbar.update()
        pbar.set_description("Processing batch %s" % str(batch_idx+1))
        if loss_criterion in ['bceloss', 'bcelosswithlogits']:
            labels = labels.float()

        # forward
        with torch.set_grad_enabled(False):
            outputs = model.forward(inputs)
            loss = criterion(outputs, labels)

        # statistics
        running_loss += loss.item() * inputs.size(1)
        if loss_criterion in ['bceloss', 'bcelosswithlogits']:
            preds = torch.where(outputs > 0.5, 1, 0).tolist()
        else:
            preds = torch.argmax(outputs, 1).tolist()
        preds_list += preds
        labels_list += labels.tolist()

    pbar.close()

    test_loss = running_loss / length_phase
    test_acc = f1_score(labels_list, preds_list, average='macro')
    test_acc = round(float(test_acc), 4)
    history_training['test_acc'] = test_acc

    history_training['y_pred'] = preds_list
    history_training['y_true'] = labels_list

    print('\nTest stats -  Loss: {:.4f} Acc: {:.2f}%'.format(test_loss, test_acc*100))
    print("Inference on Testset complete in {:.1f}s\n".format(time.time() - start_time))

    return history_training

def test_model_and_save_stats(model, model_type, loss_criterion, dataloaders, phase, field, tokenizer, stats_dict):
    """
    Testing function and save stats on the testset.
    """
    print("\n\n**TESTING**\n")

    if loss_criterion == 'bceloss':
        criterion = nn.BCELoss()
    elif loss_criterion == 'bcelosswithlogits':
        criterion = nn.BCEWithLogitsLoss()
    elif loss_criterion == 'crossentropy':
        criterion = nn.CrossEntropyLoss()
    else: # Default to BCEWithLogitsLoss
        criterion = nn.BCEWithLogitsLoss()

    print('Loss used: {}'.format(criterion))

    start_time = time.time()
    model.eval()

    running_loss = 0.0
    preds_list = []
    labels_list = []

    nb_batches = len(dataloaders[phase])
    length_phase = len(dataloaders[phase].dataset)
    assert nb_batches == length_phase, "Batch size has to be equal to 1"

    pbar = tqdm.tqdm([i for i in range(nb_batches)])

    # Iterate over data.
    for batch_idx, (inputs, labels) in enumerate(dataloaders[phase]):
        pbar.update()
        pbar.set_description("Processing batch %s" % str(batch_idx+1))
        if loss_criterion in ['bceloss', 'bcelosswithlogits']:
            labels = labels.float()

        # forward
        # track history if only in train
        with torch.set_grad_enabled(False):
            outputs = model.forward(inputs)
            loss = criterion(outputs, labels)

        # statistics
        running_loss += loss.item() * inputs.size(1)
        if loss_criterion in ['bceloss', 'bcelosswithlogits']:
            preds = torch.where(outputs > 0.5, 1, 0).tolist()
        else:
            preds = torch.argmax(outputs, 1).tolist()
        preds_list += preds
        labels_list += labels.tolist()

        # save to stats_dict
        stats_dict['original_index'].append(batch_idx)

        list_tokens = list(inputs.squeeze(0).detach().cpu())
        list_tokens = [int(tok) for tok in list_tokens]
        if model_type == 'DistillBert' and tokenizer is not None:
            text = tokenizer.decode(list_tokens)
        else:
            text = ""
            for i in range(len(list_tokens)):
                text += str(field.vocab.itos[list_tokens[i]]) + " "
        stats_dict['text'].append(text)

        stats_dict['true_label'].append(int(labels[0]))
        stats_dict['pred_label'].append(int(preds[0]))

        if loss_criterion in ['bcelosswithlogits']:
            prob = float(torch.sigmoid(outputs[0]).detach().cpu())
        elif loss_criterion in ['bceloss']:
            prob = float(outputs[0].detach().cpu())
        else:
            softmax = nn.Softmax(dim=1)
            prob = float(softmax(outputs)[0][1].detach().cpu())
        stats_dict['prob'].append(prob)

        stats_dict['loss'].append(loss.item())

    pbar.close()

    test_loss = running_loss / length_phase
    test_acc = f1_score(labels_list, preds_list, average='macro')
    test_acc = round(float(test_acc), 4)

    print('\nTest stats -  Loss: {:.4f} Acc: {:.2f}%'.format(test_loss, test_acc*100))
    print("Inference on Testset complete in {:.1f}s\n".format(time.time() - start_time))

    return stats_dict

# Inspired from https://github.com/Bjarten/early-stopping-pytorch
class EarlyStopping:
    """Early stops the training if validation loss doesn't improve after a given patience."""
    def __init__(self, patience=7, verbose=False, delta=0, save_condition='loss', path=SAVED_MODELS_PATH+'checkpoint.pt'):
        """
        Args:
            patience (int): How long to wait after last time validation loss improved.
                            Default: 7
            verbose (bool): If True, prints a message for each validation loss improvement. 
                            Default: False
            delta (float): Minimum change in the monitored quantity to qualify as an improvement.
                            Default: 0
            path (str): Path for the checkpoint to be saved to.
                            Default: 'checkpoint.pt'
        """
        self.patience = patience
        self.verbose = verbose
        self.counter = 0
        self.best_score = None
        self.early_stop = False
        self.score_min = np.Inf
        self.delta = delta
        self.path = path
        self.save_condition = save_condition
        assert self.save_condition in ['acc', 'loss']

    def __call__(self, val_loss, val_acc, model):
        if self.save_condition == 'loss':
            score = -val_loss
        elif self.save_condition == 'acc':
            score = val_acc

        if self.best_score is None:
            self.best_score = score
            self.save_checkpoint(val_loss, val_acc, model)
        elif score < self.best_score + self.delta:
            self.counter += 1
            print(f'EarlyStopping counter: {self.counter} out of {self.patience}')
            if self.counter >= self.patience:
                self.early_stop = True
        else:
            self.best_score = score
            self.save_checkpoint(val_loss, val_acc, model)
            self.counter = 0

    def save_checkpoint(self, val_loss, val_acc, model):
        '''Saves model when validation loss decrease.'''

        if not os.path.exists('saved-models'):
            os.makedirs('saved-models')

        if self.verbose:
            if self.save_condition == 'loss':
                print(f'Validation loss decreased ({self.score_min:.6f} --> {val_loss:.6f}).  Saving model ...')
            elif self.save_condition == 'acc':
                print(f'Validation acc increased ({self.score_min:.6f} --> {val_acc:.6f}).  Saving model ...')
        torch.save(model.state_dict(), 'saved-models/model.pth')
        self.score_min = val_loss
