"""
ResNet50 CNN model for 244x244x3 image classification
"""

import numpy as np
import tensorflow as tf
from art.classifiers import KerasClassifier
from tensorflow.keras.applications.resnet50 import ResNet50
from tensorflow.keras.layers import Lambda
from tensorflow.keras.models import Model

from armory.data.utils import maybe_download_weights_from_s3


IMAGENET_MEANS = [103.939, 116.779, 123.68]


def get_art_model(model_kwargs, wrapper_kwargs, weights_file=None):
    input = tf.keras.Input(shape=(224, 224, 3))

    # Preprocessing layers
    img_scaled_to_255 = Lambda(lambda image: image * 255)(input)
    # Reorder image channels i.e. img = img[..., ::-1]
    img_channel_reorder = Lambda(lambda image: tf.reverse(image, axis=[-1]))(
        img_scaled_to_255
    )
    # Model was trained with inputs zero-centered on ImageNet mean
    img_normalized = Lambda(lambda image: image - IMAGENET_MEANS)(img_channel_reorder)

    resnet50 = ResNet50(weights=None, input_tensor=img_normalized, **model_kwargs)
    model = Model(inputs=input, outputs=resnet50.output)

    if weights_file:
        filepath = maybe_download_weights_from_s3(weights_file)
        model.load_weights(filepath)

    wrapped_model = KerasClassifier(
        model,
        clip_values=(
            np.array(
                [
                    0.0 - IMAGENET_MEANS[0],
                    0.0 - IMAGENET_MEANS[1],
                    0.0 - IMAGENET_MEANS[2],
                ]
            ),
            np.array(
                [
                    255.0 - IMAGENET_MEANS[0],
                    255.0 - IMAGENET_MEANS[1],
                    255.0 - IMAGENET_MEANS[2],
                ]
            ),
        ),
        **wrapper_kwargs,
    )
    return wrapped_model
