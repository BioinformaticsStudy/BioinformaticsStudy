import os
import torch 
import numpy as np
import torch.nn as nn
import torch.nn.functional as F
import torch.optim as optim
import correlation

# settings
class Config(object):
    #Dimentions: 473034 303236 9607 8105 8195. 
    input_dim = 473034 #the number of biological makers
    hidden_dim = 200   #the number of neuro in hidden layer 
    train_file_path = './../data/sample_training.csv' #training file path
    test_file_path = './../data/sample_test.csv' #test file path
    output_dim = 1     #the output is the predicted age
    epoch_num = 200    #number of epoch 
    learning_rate = 0.01 #learning rate 
    alpha = 5 #penality parameter
    l1_ratio = 0 #l1 penality ratio
    batch_size = 20 #batch size
    cor = 0.3 #correlation threshod that select CpG sites for learning
    num_sites = 20000 #top high correlation site that selected for learning 
    use_gpu = True  # use GPU or not


class neural_network_CPNFN(nn.Module):
    #initialize neural network structure
    def __init__(self, input_dim, hidden_dim,output_dim, indexes):
        super(neural_network, self).__init__()
        self.fc1 = nn.Linear(input_dim, hidden_dim) #initialize first layer
        self.fc2 = nn.Linear(hidden_dim,output_dim) #initialize second layer

    #initialize weights
    def init_weights(self):
        init.xavier_normal(self.fc1.weight) #initialize first layer weight Xavier initialization
        init.xavier_normal(self.fc2.weight) #initialize second layer weight Xavier initialization
    
    #forward propogation
    def forward(self, x_in, corr, indexes, counter, apply_softmax=False):
       
        a_1 = F.leaky_relu(self.fc1(x_in))  # activaton function added!
        y_pred = F.leaky_relu(self.fc2(a_1)) #prediction
        self.l1_penalty = torch.norm(self.fc1.weight,1) #l1 penality
        self.l2_penalty = torch.norm(self.fc1.weight,2) #l2 penality
        self.corr_l1_penalty = torch.sum(torch.sum(torch.abs(self.fc1.weight), dim = 0)[indexes]) #corr lasso penality
        self.corr_l2_penalty = torch.sum(torch.sum((self.fc1.weight)**2, dim = 0)[counter]) #corr ridge penality
        if apply_softmax:
            y_pred = F.softmax(y_pred, dim=1) #apply softmax to the prediction

        return y_pred

#neural network trainer
class Trainer(object):
    #initialize trainer parameters
    def __init__(self,epoch,model,batch_size):
        self.model = model #initialize model
        self.epoch = epoch #initialize epoch
        self.optimizer = optim.Adam(self.model.parameters()) #initialize optimizer
        self.loss_fn = nn.MSELoss() #initialize loss function
        self.batch_size = batch_size #initialize batch size
    
    #online training
    def train_one_by_one(self,x_train,y_train, alpha=0.0, l1_ratio=0.0):
        for t in range(0,self.epoch):
            loss = 0 #initialize loss
            correct = 0 #initialize number of correct prediction
            for i in range(0,len(x_train)): #loop through all training samples
                y_pred = self.model(x_train[i,:], correlation) #get prediction from neural network
                #Accuracy
                if abs(y_pred - y_train[i,:]) < 3:
                    correct += 1
                # Loss
                #penalty = alpha*(l1_ratio*self.model.l1_penalty+(1-l1_ratio)*self.model.l2_penalty)
                loss = self.loss_fn(y_pred, y_train[i,:])#+penalty
                # Zero all gradients
                self.optimizer.zero_grad()
                #Backward propogation
                loss.backward()
                # Update weights
                self.optimizer.step()
                                # Verbose
            if (t%20==0):
                # Print the gredient
                print(self.model.fc1.weight.grad)
                print ("epoch: {0:02d} | loss: {1:.2f} | acc: {2:.1f}".format(t, loss, correct / len(y_train)))
    #batch training
    def train_by_random(self, train, correlation, indexes, complement_index, alpha=0.0, beta = 0.0,  l1_ratio=0.0):
        for t in range(0,self.epoch):
            from math import ceil
            loss = 0 #initialize loss
            correct = 0 #initialize number of correct prediction
            acc = 0 #initialize accuracy
            random_index = torch.randperm(len(train))
            random_train = train[random_index] #shuffle training samples
            x_train = random_train[:,1:]  #select training input
            y_train = random_train[:,0].reshape(-1,1) #select training label
            for i in range(0,ceil(len(x_train) // self.batch_size)): #loop through train set by batch size
                start_index = i*self.batch_size 
                end_index = (i+1)*self.batch_size if (i+1)*self.batch_size <= len(x_train) else len(x_train)
                random_train = x_train[start_index:end_index,:] #select batch of training samples
                y_labels = y_train[start_index:end_index].reshape(-1,1)
                y_pred = self.model(random_train, correlation, indexes, complement_index)
                acc +=  torch.sum(torch.abs(torch.sub(y_labels, y_pred)))
                # Loss
                penalty = alpha * self.model.corr_l1_penalty + beta * self.model.corr_l2_penalty
                loss = self.loss_fn(y_pred, y_labels)+penalty
                # Zero all gradients
                self.optimizer.zero_grad()
                #Backward pass
                loss.backward()
                # Update weights
                self.optimizer.step()
                                # Verbose
            if (t%20==0):
                print ("epoch: {0:02d} | loss: {1:.2f} | acc: {2:.2f}".format(t, loss, acc / len(y_train)))

    @staticmethod
    def get_accuracy(y_labels,y_pred):
        difference = torch.abs(y_labels-y_pred)
        correct = sum(list(map(lambda x: 1 if x<2 else 0,difference)))
        return correct

    def test(self,x_test,y_test, correlation, indexes, complement_indexes):
        model = self.model.eval()
        pred_test = model(x_test, correlation, indexes, complement_indexes)
        x = torch.cat([pred_test,y_test],1)
        x_arr = x.cpu().data.numpy()
        x_sz = len(x_arr)
        sum = 0
        for i in x_arr:
            print(i[1],i[0],abs(i[1]-i[0]))
            sum += abs(i[1]-i[0])

        print(sum/x_sz)

if torch.cuda.is_available():
    print("GPU is available to use!\n")
else:
    print("GPU is not available to use.\n")

opt = Config()

print('alpha', opt.alpha)
print('beta', opt.beta)
print('epoch', opt.epoch_num)

device = None
if opt.use_gpu and torch.cuda.is_available():
    device = torch.device('cuda')  
    torch.set_default_tensor_type('torch.cuda.FloatTensor')
else: 
    device = torch.device('cpu')

train = np.loadtxt(opt.train_file_path, skiprows=1, delimiter=',')
print("Finish read training set")
test = np.loadtxt(opt.test_file_path, skiprows=1, delimiter=',')
print("Finish read test set")
spearman_corr,pearson_corr = correlation.calculate_correlation(train) 

spearman_index = [x for x in range(len(spearman_corr)) if abs(spearman_corr[x])<opt.cor]
print(len(spearman_index))
spearman_complement_index = [x for x in range(len(spearman_corr)) if abs(spearman_corr[x])>opt.cor]
pearson_index = [x for x in range(len(pearson_corr)) if abs(pearson_corr[x])<opt.cor]
pearson_complement_index = [x for x in range(len(pearson_corr)) if abs(pearson_corr[x])>opt.cor]
train = torch.from_numpy(train).float().to(device)
test = torch.from_numpy(test).float().to(device)
spearman_corr = torch.from_numpy(spearman_corr).float().to(device)
pearson_corr = torch.from_numpy(pearson_corr).float().to(device)

print(train.shape)
print(test.shape)

x_train = train[:,1:]
y_train = train[:,0].reshape(-1,1)
x_test = test[:,1:]
y_test = test[:,0].reshape(-1,1)

model = neural_network_CPFNN(input_dim=opt.input_dim,hidden_dim=opt.hidden_dim,output_dim=opt.output_dim, indexes = spearman_index).to(device)

trainer = Trainer(epoch=opt.epoch_num,model=model,batch_size=opt.batch_size)
trainer.train_by_random(train, spearman_corr, spearman_index, spearman_complement_index, alpha =  opt.alpha, beta = opt.beta, l1_ratio =  opt.l1_ratio )
trainer.test(x_test, y_test, spearman_corr, spearman_index, spearman_complement_index)

