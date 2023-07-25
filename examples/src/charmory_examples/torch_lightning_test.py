"""
Example of PyTorch Lightning Data and ML pipeline on Food101 Dataset. Includes support for differing size of training datasets.
Provide the step you would like for the training dataset as a command line argument (do not specify a step arg if you would like to train on the whole trainset)
"""

import torch
import torchvision
from torchvision import datasets
import torchvision.transforms
import torch.nn as nn
import torch.nn.functional as F
from torch.utils.data import DataLoader
import torch.optim as optim
import pytorch_lightning as pl
import sys


def get_step():
    if len(sys.argv) == 1:
        return 1
    else:
        try:
            return int(sys.argv[1])
        except:
            return 1


class FoodClassifier(pl.LightningModule):
    def __init__(self):
        # Loosely adapted from the CIFAR10 Baseline model
        self.correct_predictions = 0
        super(FoodClassifier, self).__init__()
        self.conv1 = nn.Conv2d(3, 16, 3, stride=2, padding=1)
        self.conv2 = nn.Conv2d(16, 32, 3, stride=1, padding=1)
        self.fc1 = nn.Linear(131072, 256)
        self.fc2 = nn.Linear(256, 101)

    def forward(self, x):
        x = self.conv1(x)
        x = F.relu(x)
        x = F.max_pool2d(x, 2)
        x = self.conv2(x)
        x = F.relu(x)
        x = F.max_pool2d(x, 2)
        x = torch.flatten(x, 1)
        x = self.fc1(x)
        x = F.relu(x)
        x = self.fc2(x)
        x = F.relu(x)
        output = F.log_softmax(x, dim=1)
        return output

    def training_step(self, batch, batch_idx):
        inputs, labels = batch
        outputs = self(inputs)
        loss = F.cross_entropy(outputs, labels)
        self.log("train_loss", loss)
        return loss

    def configure_optimizers(self):
        return optim.SGD(self.parameters(), lr=0.001, momentum=0.9)

    def prepare_data(self):
        transform = torchvision.transforms.Compose(
            [
                torchvision.transforms.ToTensor(),
                torchvision.transforms.Resize(size=(512, 512)),
            ]
        )
        self.training_data = datasets.Food101(
            root="/home/rahul/cache", split="train", download=True, transform=transform
        )
        self.test_data = datasets.Food101(
            root="/home/rahul/cache", split="test", download=True, transform=transform
        )
        # Alter the download fields and the root to where the dataset is downloaded.

    def train_dataloader(self):
        """return a shuffled Dataloader for the training dataset using some subset of the training dataset"""
        mask = list(range(0, len(self.training_data), get_step()))
        masked_training_set = torch.utils.data.Subset(self.training_data, mask)
        return DataLoader(masked_training_set, shuffle=True)

    def test_dataloader(self):
        """return a shuffled Dataloader for the testing dataset"""
        return DataLoader(self.test_data, shuffle=False)

    def test_step(self, batch, batch_idx):
        inputs, labels = batch
        outputs = self(inputs)
        _, predictions = torch.max(outputs, 1)
        correct_pred = torch.sum(predictions == labels)
        total_pred = labels.numel()
        self.correct_predictions += correct_pred.item()
        return correct_pred, total_pred

    def get_testing_accuracy(self) -> float:
        return float(self.correct_predictions / 25250)


trainer = pl.Trainer(max_epochs=5, accelerator="auto", devices="auto", strategy="auto")
model = FoodClassifier()
trainer.fit(model)
trainer.test(model)
print(model.get_testing_accuracy())
"""
checkpoint_path = "1_epoch_full_train.ckpt"
trained_model = model.load_from_checkpoint(checkpoint_path)
trainer.test(trained_model)
print(trained_model.get_testing_acc())
"""
