import os
from armory.scenarios.poison import Poison
from armory.logs import log
from armory.utils import config_loading
from armory import paths
from art.utils import to_categorical 
import numpy as np



class DatasetPoisonerWitchesBrew():
    def __init__(self, attack, x_test, y_test, source_class, target_class, data_filepath):
        """
        Individual source-class triggers are chosen from x_test.  At poison time, the
        train set is modified to induce misclassification of the triggers as target_class.

        """
        self.attack = attack
        self.x_test = x_test
        self.y_test = y_test
        self.source_class = source_class
        self.target_class = target_class
        self.data_filepath = data_filepath


    def poison_dataset(self, x_train, y_train, trigger_index, return_index=True):
        """
        Return a poisoned version of dataset x, y
            if return_index, return x, y, index
        """
        if len(x_train) != len(y_train):
            raise ValueError("Sizes of x and y do not match")
        
        x_trigger = self.x_test[trigger_index]
        if len(x_trigger.shape) == 3:
            x_trigger = np.expand_dims(x_trigger, axis=0)

        y_trigger  = to_categorical([self.target_class], nb_classes=len(np.unique(y_train)))

        # TODO is armory data oriented and scaled right for art_experimental
        poison_x, poison_y, poison_index, returned_trigger_index = self.attack.poison(self.data_filepath, x_trigger, y_trigger, x_train, y_train, trigger_index) 
        

        if returned_trigger_index != trigger_index:
            # We loaded a presaved dataset, but it was trained for a different trigger
            # TODO move this into attack.poison probably
            # TODO also check that target and source class are the same...
            raise ValueError(f"The trigger image index requested in the config ({trigger_index}) "
            + f"does not match the trigger image index from the saved adversarial dataset ({returned_trigger_index}).  "
            + "Please clarify your intent by updating adhoc['trigger_index'] or attack['kwargs']['data_filepath'] in the config. "
            )

        # Return trigger_index to make sure 
        if return_index:
            return poison_x, poison_y, trigger_index, poison_index
        return poison_x, poison_y, trigger_index


# TODO Config: decide what goes in adhoc vs attack kwargs


class CifarWitchesBrew(Poison):

    def load_poisoner(self):
        adhoc_config = self.config.get("adhoc") or {}
        attack_config = self.config["attack"]
        if attack_config.get("type") == "preloaded":
            raise ValueError("preloaded attacks not currently supported for poisoning")

        self.use_poison = bool(adhoc_config["poison_dataset"])
        self.source_class = adhoc_config["source_class"]
        self.target_class = adhoc_config["target_class"]

        dataset_config = self.config["dataset"]
        test_dataset = config_loading.load_dataset(
            dataset_config, split="test", num_batches=None, **self.dataset_kwargs,
        )
        x_test, y_test = (np.concatenate(z, axis=0) for z in zip(*list(test_dataset)))

        # TODO how to pick or set trigger images
        trigger_index = adhoc_config["trigger_index"]
        if isinstance(trigger_index, int):
            trigger_index = [trigger_index]
        self.trigger_index = trigger_index


        if (y_test[self.trigger_index] != self.source_class).any():
            raise ValueError(f"Trigger image does not belong to source class (class {y_test[self.trigger_index]} != class {self.source_class})")


        if self.use_poison:

            attack_config["kwargs"]["percent_poison"] = adhoc_config["fraction_poisoned"]
            
            data_filepath = attack_config['kwargs'].pop('data_filepath') if 'data_filepath' in attack_config['kwargs'].keys() else None

            attack = config_loading.load_attack(attack_config, self.model)
            if data_filepath is not None:
                data_filepath = os.path.join(paths.runtime_paths().dataset_dir, data_filepath)
            self.poisoner = DatasetPoisonerWitchesBrew(
                attack,
                x_test,
                y_test,
                self.source_class,
                self.target_class,
                data_filepath,
            )
            self.test_poisoner = self.poisoner

    def poison_dataset(self):
        
        if self.use_poison:
            (
                self.x_poison,
                self.y_poison,
                self.trigger_index,
                self.poison_index,
            ) = self.poisoner.poison_dataset(
                self.x_clean, self.y_clean, self.trigger_index, return_index=True
            )
        else:
            self.x_poison, self.y_poison, self.poison_index = (
                self.x_clean,
                self.y_clean,
                np.array([]),
            )


    def load(self):
        self.set_random_seed()
        self.set_dataset_kwargs()
        self.load_model()
        self.load_train_dataset()
        self.load_poisoner()
        self.load_metrics()
        self.poison_dataset()
        self.filter_dataset()
        self.fit()
        self.load_dataset()


    def load_dataset(self, eval_split_default="test"):
        # Over-ridden because we need batch_size = 1 for the test set for this attack.

        dataset_config = self.config["dataset"]
        dataset_config['batch_size'] = 1 # TODO see if this persists to results config, if so make copy of dataset_config here
        eval_split = dataset_config.get("eval_split", eval_split_default)
        log.info(f"Loading test dataset {dataset_config['name']}...")
        self.test_dataset = config_loading.load_dataset(
            dataset_config,
            split=eval_split,
            num_batches=self.num_eval_batches,
            **self.dataset_kwargs,
        )
        self.i = -1


    def run_benign(self):
        # Called for all non-triggers

        x, y = self.x, self.y

        x.flags.writeable = False
        y_pred = self.model.predict(x, **self.predict_kwargs)

        self.benign_validation_metric.add_results(y, y_pred)
        # source = y == self.source_class
        # # NOTE: uses source->target trigger
        # if source.any():
        #     self.target_class_benign_metric.add_results(y[source], y_pred[source])

        # self.y_pred = y_pred
        # self.source = source
        # TODO I don't _think_ we need the above for this attack, but we need to discuss metrics more with the group

        for y_, y_pred_ in zip(y, y_pred):
            if y_ not in self.benign_test_accuracy_per_class.keys():
                self.benign_test_accuracy_per_class[y_] = []

            self.benign_test_accuracy_per_class[y_].append(
                y_ == np.argmax(y_pred_, axis=-1)
            )

    def run_attack(self):
        # Only called for the trigger images

        x, y = self.x, self.y
        print(y)
        print(self.source_class)

        
        x.flags.writeable = False
        y_pred_adv = self.model.predict(x, **self.predict_kwargs)
        print(y_pred_adv)
        print(self.target_class)

        self.poisoned_test_metric.add_results(y, y_pred_adv)
        # # NOTE: uses source->target trigger
        # if source.any():
        #     self.poisoned_targeted_test_metric.add_results(
        #         [self.target_class] * source.sum(), y_pred_adv[source]
        #     )
        # Pretty positive we don't need the above, since this is only called for images from source class anyway, that's all poisoned_test_metric will have.


        self.y_pred_adv = y_pred_adv


    def evaluate_current(self):
        # plan
        # use test set batch size of 1
        # if self.i is not in trigger_index:
        #   run_benign
        # otherwise,
        #   run attack

        if self.i in self.trigger_index:
            self.run_attack()
        else:
            self.run_benign()




