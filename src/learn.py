from __future__ import division
print "1"
import time
import numpy as np
print "2"
import matplotlib
matplotlib.use('Agg')
print "3"
import matplotlib.pyplot as plt
import os
import scipy.misc
import metrics
import util
import logging

if __name__ == "__main__":
    print "4"
    from dataset import load_images
    import theano
    import theano.tensor as T
    print "5"
    import lasagne
    print "6"
    import unet
    print "7"
    from unet import INPUT_SIZE, OUTPUT_SIZE


from tqdm import tqdm
from glob import glob
print "8"

import cPickle as pickle
from parallel import ParallelBatchIterator
print "9"

if __name__ == "__main__":
    # create Theano variables for input and target minibatch
    input_var = T.tensor4('inputs')
    target_var = T.tensor4('targets', dtype='int64')
    weight_var = T.tensor4('weights')

    logging.info("Defining network")
    net_dict = unet.define_network(input_var)
    network = net_dict['out']

    train_fn, val_fn = unet.define_updates(network, input_var, target_var, weight_var)

    model_name = 'unet'+str(int(time.time()))
    model_folder = os.path.join('../data/models',model_name)
    plot_folder = os.path.join('../images/plot',model_name)

    folders = ['../images','../images/plot','../data','../data/models', model_folder, plot_folder]
    map(util.make_dir_if_not_present, folders)
    logging.basicConfig(filename="../data/log{0}.txt".format(model_name),level=logging.DEBUG,format='%(asctime)s %(message)s')

    np.random.seed(1)
    folder_train = './../data/1_1_1mm_512_x_512_lung_slices/subset[0-2]/'
    filenames_train = glob(folder_train+ '*.pkl.gz')
    #print filenames
    folder_val = './../data/1_1_1mm_512_x_512_lung_slices/subset[3]/'
    filenames_val = glob(folder_val+ '*.pkl.gz')

    np.random.shuffle(filenames_train)
    np.random.shuffle(filenames_val)

    train_batch_size = 1
    val_batch_size = 2

    train_subset = None
    val_subset = None

    num_epochs = 400

    filenames_train = filenames_train[:train_subset]
    filenames_val = filenames_val[:val_subset]

    metric_names = ['Loss  ','L2    ','Accuracy','Dice  ','Precision','Recall']
    train_metrics_all = []
    val_metrics_all = []

    logging.info("Starting training...")
    for epoch in range(num_epochs):
        # In each epoch, we do a full pass over the training data:
        train_batches = 0
        start_time = time.time()

        np.random.shuffle(filenames_train)
        train_gen = ParallelBatchIterator(load_images, filenames_train, ordered=True, batch_size=train_batch_size, multiprocess=False)

        train_metrics = []
        val_metrics = []

        for i, batch in enumerate(tqdm(train_gen)):
            inputs, targets, weights = batch

            err, l2_loss, acc, dice, true, prob, prob_b = train_fn(inputs, targets, weights)
            tp,tn,fp,fn = metrics.calc_errors(true, prob_b)

            train_metrics.append([err, l2_loss, acc, dice, tp, tn, fp, fn])
            train_batches += 1

            if i % 10 == 0:
                im = np.hstack((
                    true[:OUTPUT_SIZE**2].reshape(OUTPUT_SIZE,OUTPUT_SIZE),
                    prob[:OUTPUT_SIZE**2][:,1].reshape(OUTPUT_SIZE,OUTPUT_SIZE)))

                plt.imsave(os.path.join(plot_folder,'train_{}_epoch{}.png'.format(model_name, epoch)),im)

        # And a full pass over the validation data:
        val_batches = 0

        np.random.shuffle(filenames_val)
        val_gen = ParallelBatchIterator(load_images, filenames_val, ordered=True, batch_size=val_batch_size,multiprocess=False)

        for i, batch in enumerate(tqdm(val_gen)):
            inputs, targets, weights = batch

            err, l2_loss, acc, dice, true, prob, prob_b = val_fn(inputs, targets, weights)
            tp,tn,fp,fn = metrics.calc_errors(true, prob_b)

            val_metrics.append([err, l2_loss, acc, dice, tp, tn, fp, fn])
            val_batches += 1

            if i % 30 == 0: #Create image every 10th image
                im = np.hstack((
                    true[:OUTPUT_SIZE**2].reshape(OUTPUT_SIZE,OUTPUT_SIZE),
                    prob[:OUTPUT_SIZE**2][:,1].reshape(OUTPUT_SIZE,OUTPUT_SIZE)))

                plt.imsave(os.path.join(plot_folder,'val_{}_epoch{}.png'.format(model_name, epoch)),im)
                plt.close()

        train_metrics = np.sum(np.array(train_metrics),axis=0)/train_batches
        val_metrics = np.sum(np.array(val_metrics),axis=0)/val_batches

        precision_train = train_metrics[4] / (train_metrics[4]+train_metrics[6])
        recall_train = train_metrics[4] / (train_metrics[4]+train_metrics[7])

        precision_val = val_metrics[4] / (val_metrics[4]+val_metrics[6])
        recall_val = val_metrics[4] / (val_metrics[4]+val_metrics[7])

        train_metrics = list(train_metrics[:4]) + [precision_train,recall_train] #Strip off false positives et al
        val_metrics = list(val_metrics[:4]) + [precision_val,recall_val]

        # Then we print the results for this epoch:
        logging.info("\nEpoch {} of {} took {:.3f}s".format(
            epoch + 1, num_epochs, time.time() - start_time))

        #print "Metrics"
        for name, train_metric, val_metric in zip(metric_names, train_metrics, val_metrics):
            logging.info(" {}:\t\t {:.6f}\t{:.6f}".format(name,train_metric,val_metric))

        if epoch % 4 == 0:
            logging.info("Saving model")
            np.savez(os.path.join(model_folder,'{}_epoch{}.npz'.format(model_name, epoch)), *lasagne.layers.get_all_param_values(network))

        train_metrics_all.append(train_metrics)
        val_metrics_all.append(val_metrics)

        for name, train_vals, val_vals in zip(metric_names, zip(*train_metrics_all),zip(*val_metrics_all)):
            plt.figure()
            plt.plot(train_vals)
            plt.plot(val_vals)
            plt.ylabel(name)
            plt.xlabel("Epoch")

            plt.savefig(os.path.join(plot_folder, '{}.png'.format(name)))
            plt.close()


    # Optionally, you could now dump the network weights to a file like this:
    # np.savez('model.npz', *lasagne.layers.get_all_param_values(network))
    #
    # And load them again later on like this:
    # with np.load('model.npz') as f:
    #     param_values = [f['arr_%d' % i] for i in range(len(f.files))]
    # lasagne.layers.set_all_param_values(network, param_values)