'''
Created byu greg-ogs
'''
import numpy as np
import os
import time
import tensorflow as tf
import matplotlib.pyplot as plt
from tensorflow.keras.layers import Conv2D, MaxPooling2D, Flatten, Dense
import PIL.Image as im

class ManualImageChecker:
    def __init__(self, image_path: str = "/app/infra/local/mysql-database/datasets/image-datasets/laser-spots"):
        self.model = tf.keras.models.load_model("./tf-model/160-by-128-model.keras")
        self.model.summary()
        self.images_path = image_path

    def predict(self):
        image = im.open(self.image_path).convert("RGB").resize((160, 128))
        image_array = np.array(image) / 255.0
        img_array = tf.keras.utils.img_to_array(image_array)
        img_arr = tf.expand_dims(img_array, 0)
        prediction = self.model.predict(img_arr)
        return prediction

    def img_to_plot(self, predictions):
        image_to_plot = im.open(self.image_path).convert("RGB")
        self.x = predictions[0][0]
        self.y = predictions[0][1]
        plt.rcParams.update({'font.size': 30})
        fig = plt.figure("Printing figure and coordinates", figsize=(11, 12.8))
        ax = fig.add_subplot(1, 1, 1)
        ax.imshow(image_to_plot, origin='lower')
        plt.plot(self.x, self.y, marker='o', markersize=15, color='red')  # Swap X and Y for the rotated plot
        # plt.title("Superpixels -- SLIC (%d segments)" % (self.n_segments))
        plt.xlabel("pixels")
        plt.ylabel("pixels")
        plt.axis("on")
        plt.show()
        
    def main(self):
        for filename in os.listdir(self.images_path):
            if filename.lower().endswith('.png'):
                self.image_path = os.path.join(self.images_path, filename)
            predictions = self.predict()
            self.img_to_plot(predictions)
            time.sleep(1)

img_checker_instance = ManualImageChecker()
img_checker_instance.main()